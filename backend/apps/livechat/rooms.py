"""Group chat — the only place rooms, messages and moderation change.

Rooms have an audience: everyone (every logged-in player), agents (active
affiliates) or staff. Staff read and post everywhere. Staff can hide a message
(out of view for everyone but staff, reversible), delete it for good, pin it,
and mute a player (they can still read). Players can report a message. Posting
is rate-limited per room (slow mode) and overall, and refuses repeats.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q
from django.utils import timezone

from apps.accounts import services as accounts_services

from . import utils
from .models import ChatMute, ChatRoom, MessageReport, RoomMessage, RoomRead

MAX_LENGTH = 500
PER_TEN_MINUTES = 40
REPEAT_WINDOW = timedelta(seconds=60)
PAGE = 50


class ChatError(ValueError):
    """Shown to whoever tried."""

    def __init__(self, message: str, code: int = 400):
        super().__init__(message)
        self.code = code


# -- who can see what -----------------------------------------------------------

def is_agent(player_id: Optional[int]) -> bool:
    if not player_id:
        return False
    from apps.affiliates.models import Affiliate
    return Affiliate.objects.filter(player_id=player_id, status=Affiliate.Status.ACTIVE).exists()


def role_of(player_id: Optional[int], *, staff: bool = False) -> str:
    return 'staff' if staff else 'agent' if is_agent(player_id) else 'player'


def rooms_for(*, player_id: Optional[int], staff: bool = False):
    """The rooms this person may read."""
    if staff:
        return ChatRoom.objects.all()
    audiences = [ChatRoom.Audience.EVERYONE]
    if is_agent(player_id):
        audiences.append(ChatRoom.Audience.AGENTS)
    return ChatRoom.objects.filter(is_open=True, audience__in=audiences)


def room_for(slug_or_id, *, player_id: Optional[int], staff: bool = False) -> ChatRoom:
    qs = rooms_for(player_id=player_id, staff=staff)
    room = qs.filter(pk=slug_or_id).first() if isinstance(slug_or_id, int) else qs.filter(slug=slug_or_id).first()
    if room is None:
        raise ChatError('That room isn’t available.', 404)
    return room


def mute_of(player_id: Optional[int], *, now=None) -> Optional[ChatMute]:
    """The player's active mute, if any (an expired one is cleared)."""
    if not player_id:
        return None
    mute = ChatMute.objects.filter(player_id=player_id).first()
    if mute and mute.until and mute.until <= (now or timezone.now()):
        mute.delete()
        return None
    return mute


# -- reading --------------------------------------------------------------------

def message_row(m: RoomMessage, *, staff: bool = False, me: Optional[int] = None) -> dict:
    row = {
        'id': m.id, 'body': m.body, 'sender': m.sender_name, 'role': m.sender_role, 'from_staff': m.from_staff,
        'mine': bool(me and m.player_id == me and not m.from_staff), 'pinned': m.pinned,
        'created_at': m.created_at.isoformat(),
        'reply_to': ({'id': m.reply_to_id, 'sender': m.reply_to.sender_name,
                      'body': '' if m.reply_to.hidden_at and not staff else m.reply_to.body[:120]}
                     if m.reply_to_id and m.reply_to else None),
    }
    if staff:
        row.update({'player_id': m.player_id, 'hidden': m.hidden_at is not None, 'hidden_by': m.hidden_by,
                    'hidden_reason': m.hidden_reason, 'reports': m.reports})
    return row


def messages(room: ChatRoom, *, staff: bool = False, after: Optional[int] = None, before: Optional[int] = None,
             only: str = '', limit: int = PAGE):
    """A page of messages, oldest first. `after` = newer than this id (polling);
    `before` = older (scrolling back); neither = the latest page. Hidden
    messages are left out unless `staff`."""
    qs = room.messages.select_related('reply_to')
    if not staff:
        qs = qs.filter(hidden_at__isnull=True)
    elif only == 'hidden':
        qs = qs.filter(hidden_at__isnull=False)
    elif only == 'reported':
        qs = qs.filter(reports__gt=0)
    limit = max(1, min(int(limit or PAGE), 100))
    if after is not None:
        return list(qs.filter(id__gt=after).order_by('id')[:limit])
    if before is not None:
        qs = qs.filter(id__lt=before)
    return list(reversed(list(qs.order_by('-id')[:limit])))


def pinned(room: ChatRoom, *, staff: bool = False):
    qs = room.messages.filter(pinned=True).select_related('reply_to')
    return list((qs if staff else qs.filter(hidden_at__isnull=True)).order_by('-id')[:3])


def mark_read(room: ChatRoom, player_id: int) -> None:
    last = room.messages.order_by('-id').values_list('id', flat=True).first() or 0
    RoomRead.objects.update_or_create(room=room, player_id=player_id, defaults={'last_id': last})


def room_rows(*, player_id: Optional[int], staff: bool = False) -> list[dict]:
    rooms = list(rooms_for(player_id=player_id, staff=staff))
    reads = dict(RoomRead.objects.filter(player_id=player_id, room__in=rooms).values_list('room_id', 'last_id')) if player_id else {}
    out = []
    for room in rooms:
        visible = room.messages if staff else room.messages.filter(hidden_at__isnull=True)
        last = visible.order_by('-id').first()
        row = {
            'id': room.id, 'slug': room.slug, 'name': room.name, 'description': room.description, 'audience': room.audience,
            'audience_label': room.get_audience_display(), 'staff_only_posting': room.staff_only_posting,
            'is_open': room.is_open, 'slow_mode_seconds': room.slow_mode_seconds, 'sort_order': room.sort_order,
            'last': {'sender': last.sender_name, 'body': last.body[:80], 'at': last.created_at.isoformat()} if last else None,
            'unread': visible.filter(id__gt=reads.get(room.id, 0)).exclude(player_id=player_id).count() if player_id else 0,
        }
        if staff:
            counts = room.messages.aggregate(total=Count('id'), hidden=Count('id', filter=Q(hidden_at__isnull=False)),
                                             reported=Count('id', filter=Q(reports__gt=0, hidden_at__isnull=True)))
            row.update(counts)
        out.append(row)
    return out


# -- posting --------------------------------------------------------------------

def _clean(body) -> str:
    text = utils._WHITESPACE.sub(' ', str(body or '')).strip()
    if not text:
        raise ChatError('Type a message first.')
    if len(text) > MAX_LENGTH:
        raise ChatError(f'Keep it under {MAX_LENGTH} characters.')
    return text


def _reply_target(room: ChatRoom, reply_to) -> Optional[RoomMessage]:
    if reply_to in (None, ''):
        return None
    try:
        return room.messages.filter(pk=int(reply_to), hidden_at__isnull=True).first()
    except (TypeError, ValueError):
        return None


def player_post(*, player, room: ChatRoom, body, reply_to=None, now=None) -> RoomMessage:
    now = now or timezone.now()
    if player.is_suspended:
        raise ChatError('Your account is suspended.', 403)
    if room.staff_only_posting:
        raise ChatError('Only our team posts in this room.', 403)
    mute = mute_of(player.id, now=now)
    if mute:
        until = f' until {timezone.localtime(mute.until):%d %b %H:%M}' if mute.until else ''
        raise ChatError(f'You can’t post in chat{until}.', 403)
    text = _clean(body)
    mine = RoomMessage.objects.filter(player_id=player.id, from_staff=False)
    last = mine.filter(room=room).order_by('-id').first()
    if last and room.slow_mode_seconds and (now - last.created_at).total_seconds() < room.slow_mode_seconds:
        raise ChatError(f'Slow mode: wait {room.slow_mode_seconds} seconds between messages.', 429)
    if mine.filter(created_at__gte=now - timedelta(minutes=10)).count() >= PER_TEN_MINUTES:
        raise ChatError('You’ve sent a lot of messages — take a short break.', 429)
    if mine.filter(room=room, body__iexact=text, created_at__gte=now - REPEAT_WINDOW).exists():
        raise ChatError('You just sent that.', 429)
    return RoomMessage.objects.create(room=room, player_id=player.id, sender_name=player.username[:150],
                                      sender_role=role_of(player.id), body=text, reply_to=_reply_target(room, reply_to))


def staff_post(*, room: ChatRoom, body, staff_name: str, reply_to=None) -> RoomMessage:
    return RoomMessage.objects.create(room=room, from_staff=True, sender_name=(staff_name or 'Staff')[:150],
                                      sender_role='staff', body=_clean(body), reply_to=_reply_target(room, reply_to))


def report(*, message_id: int, player_id: int, reason: str = '') -> None:
    """A player flags a message they can see. Counted once per player."""
    message = RoomMessage.objects.select_related('room').filter(pk=message_id, hidden_at__isnull=True).first()
    if message is None:
        raise ChatError('That message is gone.', 404)
    room_for(message.room_id, player_id=player_id)          # they must be able to read the room
    if message.player_id == player_id and not message.from_staff:
        raise ChatError('That’s your own message.')
    try:
        with transaction.atomic():
            MessageReport.objects.create(message=message, player_id=player_id, reason=(reason or '').strip()[:200])
            RoomMessage.objects.filter(pk=message.pk).update(reports=F('reports') + 1)
    except IntegrityError:
        pass  # already reported by this player


# -- moderation (staff) ---------------------------------------------------------

def _audit(action: str, request, message: RoomMessage, **extra) -> None:
    accounts_services.audit(message.player_id, f'chat_message_{action}', request, room=message.room.slug,
                            message_id=message.id, sender=message.sender_name, **extra)


def moderate(ids, *, action: str, by: str, reason: str = '', request=None) -> dict:
    """hide | unhide | delete | pin | unpin a set of messages. Hiding keeps the
    message for staff and can be undone; deleting removes it for good (the audit
    log keeps who sent it and who deleted it, not what it said)."""
    if action not in ('hide', 'unhide', 'delete', 'pin', 'unpin'):
        raise ChatError('Choose hide, unhide, delete, pin or unpin.')
    done = 0
    for message in RoomMessage.objects.select_related('room').filter(pk__in=list(ids)[:200]):
        if action == 'hide':
            if message.hidden_at:
                continue
            message.hidden_at, message.hidden_by, message.hidden_reason = timezone.now(), by[:150], (reason or '').strip()[:200]
            message.pinned = False
            message.save(update_fields=['hidden_at', 'hidden_by', 'hidden_reason', 'pinned'])
        elif action == 'unhide':
            if not message.hidden_at:
                continue
            message.hidden_at, message.hidden_by, message.hidden_reason = None, '', ''
            message.save(update_fields=['hidden_at', 'hidden_by', 'hidden_reason'])
        elif action in ('pin', 'unpin'):
            message.pinned = action == 'pin' and message.hidden_at is None
            message.save(update_fields=['pinned'])
        _audit({'hide': 'hidden', 'unhide': 'unhidden', 'delete': 'deleted', 'pin': 'pinned', 'unpin': 'unpinned'}[action],
               request, message, by=by, **({'reason': reason[:200]} if action == 'hide' and reason else {}))
        if action == 'delete':
            message.delete()
        done += 1
    return {'action': action, 'done': done}


def mute(*, player_id: int, by: str, minutes: Optional[int] = None, reason: str = '', request=None) -> ChatMute:
    """Stop a player posting, for `minutes` or until lifted. They can still read."""
    from apps.accounts.models import Player
    player = Player.objects.select_related('user').filter(pk=player_id).first()
    if player is None:
        raise ChatError('Player not found.', 404)
    if player.user and (player.user.is_staff or player.user.is_superuser):
        raise ChatError('Staff accounts can’t be muted.')
    until = timezone.now() + timedelta(minutes=max(1, min(int(minutes), 60 * 24 * 365))) if minutes else None
    row, _ = ChatMute.objects.update_or_create(player_id=player_id, defaults={
        'until': until, 'reason': (reason or '').strip()[:200], 'muted_by': by[:150]})
    accounts_services.audit(player_id, 'chat_muted', request, by=by, until=until.isoformat() if until else 'until lifted',
                            reason=row.reason)
    return row


def unmute(*, player_id: int, by: str, request=None) -> None:
    if ChatMute.objects.filter(player_id=player_id).delete()[0]:
        accounts_services.audit(player_id, 'chat_unmuted', request, by=by)


def mutes() -> list[dict]:
    from apps.accounts.models import Player
    rows = [m for m in ChatMute.objects.order_by('-created_at') if not (m.until and m.until <= timezone.now())]
    names = dict(Player.objects.filter(pk__in=[m.player_id for m in rows]).values_list('id', 'username'))
    return [{'player_id': m.player_id, 'username': names.get(m.player_id, '(deleted)'), 'reason': m.reason,
             'until': m.until.isoformat() if m.until else None, 'muted_by': m.muted_by, 'created_at': m.created_at.isoformat()}
            for m in rows]


ROOM_FIELDS = ('name', 'description', 'audience', 'staff_only_posting', 'is_open', 'slow_mode_seconds', 'sort_order')


def save_room(room: Optional[ChatRoom], data: dict, *, by: str, request=None) -> ChatRoom:
    """Create or edit a room."""
    from django.utils.text import slugify
    room = room or ChatRoom()
    for f in ROOM_FIELDS:
        if f not in data:
            continue
        value = data[f]
        if f in ('name', 'description'):
            value = str(value or '').strip()[:60 if f == 'name' else 200]
        elif f in ('staff_only_posting', 'is_open'):
            value = bool(value)
        elif f in ('slow_mode_seconds', 'sort_order'):
            try:
                value = int(value)
            except (TypeError, ValueError) as exc:
                raise ChatError('Enter whole numbers.') from exc
            if not 0 <= value <= (3600 if f == 'slow_mode_seconds' else 1000):
                raise ChatError('Slow mode is 0–3600 seconds.')
        elif value not in ChatRoom.Audience.values:
            raise ChatError('Choose who the room is for.')
        setattr(room, f, value)
    if len(room.name) < 2:
        raise ChatError('Give the room a name.')
    if not room.slug:
        base = slugify(room.name)[:32] or 'room'
        slug, n = base, 2
        while ChatRoom.objects.filter(slug=slug).exists():
            slug, n = f'{base}-{n}', n + 1
        room.slug = slug
    room.save()
    accounts_services.audit(None, 'chat_room_saved', request, room=room.slug, by=by,
                            **{f: str(getattr(room, f)) for f in ROOM_FIELDS})
    return room


def delete_room(room: ChatRoom, *, by: str, request=None) -> None:
    accounts_services.audit(None, 'chat_room_deleted', request, room=room.slug, by=by, messages=room.messages.count())
    room.delete()


def erase_player_data(player_id: int) -> int:
    """Account deletion: the player's messages, mute, reports and read markers."""
    deleted = RoomMessage.objects.filter(player_id=player_id, from_staff=False).delete()[0]
    ChatMute.objects.filter(player_id=player_id).delete()
    MessageReport.objects.filter(player_id=player_id).delete()
    RoomRead.objects.filter(player_id=player_id).delete()
    return deleted
