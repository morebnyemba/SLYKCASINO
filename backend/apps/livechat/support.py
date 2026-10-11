"""Private support chat: each player has one conversation with the support
team, channel "support:<player id>". Only that player and staff can read it —
there is no shared lobby."""
from __future__ import annotations

from datetime import timedelta

from django.db.models import Count, Max, Q
from django.utils import timezone

from . import utils
from .models import ChatMessage

MAX_LENGTH = 1000
MIN_GAP_SECONDS = 2
PER_TEN_MINUTES = 30


class SupportError(ValueError):
    """Shown to whoever sent the message."""


def channel_for(player_id: int) -> str:
    return f'support:{int(player_id)}'


def _clean(body: str) -> str:
    text = utils._WHITESPACE.sub(' ', str(body or '')).strip()
    if not text:
        raise SupportError('Type a message first.')
    if len(text) > MAX_LENGTH:
        raise SupportError(f'Keep it under {MAX_LENGTH} characters.')
    return text


def payload(m: ChatMessage) -> dict:
    return {
        'id': m.id, 'body': m.body, 'from_staff': m.from_staff,
        'sender': (m.staff_name or 'Support team') if m.from_staff else 'You',
        'created_at': m.created_at.isoformat(), 'read': m.read_at is not None,
    }


def thread(player_id: int, *, limit: int = 200):
    rows = ChatMessage.objects.filter(channel=channel_for(player_id)).order_by('-created_at', '-id')[:limit]
    return list(reversed(list(rows)))


def mark_read(player_id: int, *, by_staff: bool, now=None) -> int:
    """Mark the other side's messages as read."""
    return ChatMessage.objects.filter(
        channel=channel_for(player_id), from_staff=not by_staff, read_at__isnull=True,
    ).update(read_at=now or timezone.now())


def player_post(*, player_id: int, body: str, now=None) -> ChatMessage:
    now = now or timezone.now()
    text = _clean(body)
    mine = ChatMessage.objects.filter(channel=channel_for(player_id), from_staff=False)
    last = mine.order_by('-created_at').first()
    if last and (now - last.created_at).total_seconds() < MIN_GAP_SECONDS:
        raise SupportError('Slow down a little.')
    if mine.filter(created_at__gte=now - timedelta(minutes=10)).count() >= PER_TEN_MINUTES:
        raise SupportError('You’ve sent a lot of messages — our team will reply shortly.')
    return ChatMessage.objects.create(channel=channel_for(player_id), player_id=player_id, body=text)


def staff_reply(*, player_id: int, body: str, staff_name: str) -> ChatMessage:
    msg = ChatMessage.objects.create(
        channel=channel_for(player_id), player_id=player_id, body=_clean(body),
        from_staff=True, staff_name=staff_name[:150],
    )
    from apps.notifications import services as notif_services
    notif_services.notify(player_id=player_id, kind='account_alert', title='Support replied',
                          body=msg.body[:140] + ('…' if len(msg.body) > 140 else ''))
    return msg


def unread_for_player(player_id: int) -> int:
    return ChatMessage.objects.filter(channel=channel_for(player_id), from_staff=True, read_at__isnull=True).count()


def inbox(*, q: str = '', limit: int = 100) -> list[dict]:
    """Conversations for staff, newest activity first, with unread counts."""
    from apps.accounts.models import Player
    rows = (ChatMessage.objects.filter(channel__startswith='support:', player_id__isnull=False)
            .values('player_id')
            .annotate(last_at=Max('created_at'), total=Count('id'),
                      unread=Count('id', filter=Q(from_staff=False, read_at__isnull=True)))
            .order_by('-last_at'))
    if q:
        ids = list(Player.objects.filter(Q(username__icontains=q) | Q(email__icontains=q)).values_list('id', flat=True)[:500])
        rows = rows.filter(player_id__in=ids)
    rows = list(rows[:limit])
    players = {p.id: p for p in Player.objects.filter(id__in=[r['player_id'] for r in rows])}
    out = []
    for r in rows:
        last = ChatMessage.objects.filter(channel=channel_for(r['player_id'])).order_by('-created_at', '-id').first()
        p = players.get(r['player_id'])
        out.append({
            'player_id': r['player_id'], 'username': p.username if p else '(deleted)', 'email': p.email if p else '',
            'kyc_status': p.kyc_status if p else None, 'unread': r['unread'], 'messages': r['total'],
            'last_at': r['last_at'].isoformat(), 'last_body': last.body[:120] if last else '',
            'last_from_staff': bool(last and last.from_staff),
        })
    return out


def unread_threads() -> int:
    return (ChatMessage.objects.filter(channel__startswith='support:', from_staff=False, read_at__isnull=True)
            .values('player_id').distinct().count())
