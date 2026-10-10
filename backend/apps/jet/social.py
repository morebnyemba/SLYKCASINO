"""The game's social side: the chat lobby, the bot that posts each round's
biggest win, and "rain" — free bets dropped on real players who are playing
or chatting.

Rain free bets are real value, so they only ever go to real players who have
deposited, within a daily budget, and their winnings are paid as bonus
credits (see services._pay), which reports count as a promotion cost.
"""
from __future__ import annotations

import random
import re
from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from . import bots, engine
from .models import JetBet, JetChatMessage, JetChatMute, JetFreeBet, JetRound, JetSettings

BOT_NAME = 'Aviator Bot'
MAX_LENGTH = 160
HISTORY = 60
# One message every few seconds and a handful a minute per player.
MIN_GAP_SECONDS = 3
PER_MINUTE = 8
# A round's best win is announced when it's a high multiplier (5x+, $5+ won)
# or a big payout ($50+ at 2x+) — not just a large stake cashed out early.
ANNOUNCE_RULES = ((Decimal('5'), Decimal('5')), (Decimal('2'), Decimal('50')))
# Who can catch the rain: real players active in the game this recently.
RAIN_ACTIVE_MINUTES = 30
FREE_BET_HOURS = 24

LINK = re.compile(r'(https?://|www\.|\b[\w-]+\.(com|net|org|io|co|zw|me|app|xyz|bet|link)\b|t\.me|wa\.me)', re.I)
PHONE = re.compile(r'(\+?\d[\d\s-]{7,}\d)')


class ChatError(ValueError):
    """A message that can't be posted; the text is for the player."""


def _publish(payload: dict) -> None:
    from .services import publish
    publish(payload)


def message_payload(m: JetChatMessage) -> dict:
    return {'id': m.id, 'kind': m.kind, 'name': m.name, 'body': m.body, 'at': m.created_at.isoformat()}


def recent(limit: int = HISTORY) -> list[dict]:
    rows = JetChatMessage.objects.filter(hidden=False).order_by('-id')[:limit]
    return [message_payload(m) for m in reversed(list(rows))]


def _has_deposited(player_id: int) -> bool:
    from apps.wallet.models import LedgerEntry
    return LedgerEntry.objects.filter(wallet__player_id=player_id, kind='deposit').exists()


def muted_until(player_id: int, now=None):
    now = now or timezone.now()
    mute = JetChatMute.objects.filter(player_id=player_id, until__gt=now).first()
    return mute.until if mute else None


def post(*, player, body: str, now=None) -> JetChatMessage:
    now = now or timezone.now()
    if not JetSettings.load().chat_enabled:
        raise ChatError('Chat is switched off right now.')
    text = re.sub(r'\s+', ' ', str(body or '')).strip()
    if not text:
        raise ChatError('Type a message first.')
    if len(text) > MAX_LENGTH:
        raise ChatError(f'Keep it under {MAX_LENGTH} characters.')
    if LINK.search(text) or PHONE.search(text):
        raise ChatError('Links and phone numbers aren’t allowed in chat.')
    if muted_until(player.id, now):
        raise ChatError('You’re muted in chat for now.')
    if not _has_deposited(player.id):
        raise ChatError('Make your first deposit to join the chat.')
    mine = JetChatMessage.objects.filter(player_id=player.id, created_at__gte=now - timedelta(minutes=1))
    last = mine.order_by('-created_at').first()
    if last and (now - last.created_at).total_seconds() < MIN_GAP_SECONDS or mine.count() >= PER_MINUTE:
        raise ChatError('Slow down a little.')
    msg = JetChatMessage.objects.create(player_id=player.id, name=engine.mask_name(player.username), body=text)
    _publish({'type': 'chat', 'message': message_payload(msg)})
    return msg


def system_message(kind: str, body: str) -> JetChatMessage:
    msg = JetChatMessage.objects.create(kind=kind, name=BOT_NAME, body=body[:200])
    _publish({'type': 'chat', 'message': message_payload(msg)})
    return msg


def hide(message_id: int) -> bool:
    done = JetChatMessage.objects.filter(pk=message_id, hidden=False).update(hidden=True)
    if done:
        _publish({'type': 'chat_hide', 'id': message_id})
    return bool(done)


def mute(player_id: int, hours: int, by: str = '') -> JetChatMute:
    until = timezone.now() + timedelta(hours=hours)
    obj, _ = JetChatMute.objects.update_or_create(player_id=player_id, defaults={'until': until, 'by': by[:150]})
    return obj


# -- the win bot ----------------------------------------------------------------

def announce_round(rnd: JetRound, now=None):
    """Post the round's biggest win to the chat if it's worth shouting about.
    Includes simulated players' wins only while they're switched on (the game
    rules say so)."""
    now = now or timezone.now()
    cfg = JetSettings.load()
    if not cfg.chat_enabled:
        return None
    wins = [(b.payout, b.cashout_multiplier, b.display_name)
            for b in JetBet.objects.filter(round=rnd, status=JetBet.Status.CASHED)]
    wins += [(Decimal(b['payout']), Decimal(b['cashout_multiplier']), b['player'])
             for b in bots.snapshot(rnd, now, cfg) if b['status'] == 'cashed']
    worthy = [w for w in wins if any(w[1] >= x and w[0] >= p for x, p in ANNOUNCE_RULES)]
    if not worthy:
        return None
    payout, x, name = max(worthy)
    return system_message(JetChatMessage.Kind.WIN, f'{name} cashed out at {x:.2f}x and won ${payout:,.2f}!')


# -- rain -----------------------------------------------------------------------

def given_today(now=None) -> Decimal:
    now = now or timezone.now()
    start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    total = JetFreeBet.objects.filter(source='rain', created_at__gte=start).aggregate(t=Sum('amount'))['t']
    return total or Decimal('0')


def eligible_players(now=None) -> list[int]:
    """Real players who bet with money or chatted recently, have deposited and aren't muted."""
    from apps.wallet.models import LedgerEntry
    now = now or timezone.now()
    since = now - timedelta(minutes=RAIN_ACTIVE_MINUTES)
    ids = set(JetBet.objects.filter(created_at__gte=since, is_free=False).values_list('player_id', flat=True))
    ids |= set(JetChatMessage.objects.filter(created_at__gte=since, kind=JetChatMessage.Kind.CHAT)
               .exclude(player_id=None).values_list('player_id', flat=True))
    if not ids:
        return []
    deposited = set(LedgerEntry.objects.filter(kind='deposit', wallet__player_id__in=ids)
                    .values_list('wallet__player_id', flat=True).distinct())
    muted = set(JetChatMute.objects.filter(player_id__in=ids, until__gt=now).values_list('player_id', flat=True))
    return sorted(deposited - muted)


@transaction.atomic
def rain(*, players: int | None = None, amount=None, now=None) -> dict:
    """Drop free bets on up to `players` random eligible players, within the
    day's budget. Returns {'given': n, 'amount': str, 'reason': str|None}."""
    from apps.accounts.models import Player
    now = now or timezone.now()
    cfg = JetSettings.objects.select_for_update().get(pk=JetSettings.load().pk)
    amount = Decimal(str(amount if amount is not None else cfg.rain_amount)).quantize(engine.CENT)
    players = int(players if players is not None else cfg.rain_players)
    cfg.last_rain_at = now
    cfg.save(update_fields=['last_rain_at'])
    if amount <= 0 or players <= 0:
        return {'given': 0, 'amount': str(amount), 'reason': 'Set an amount and a number of players.'}
    left = cfg.rain_daily_budget - given_today(now)
    n = min(players, int(left // amount) if left > 0 else 0)
    if n <= 0:
        return {'given': 0, 'amount': str(amount), 'reason': 'Today’s rain budget is used up.'}
    pool = eligible_players(now)
    if not pool:
        return {'given': 0, 'amount': str(amount), 'reason': 'Nobody is playing or chatting right now.'}
    lucky = random.SystemRandom().sample(pool, min(n, len(pool)))
    expires = now + timedelta(hours=FREE_BET_HOURS)
    JetFreeBet.objects.bulk_create([JetFreeBet(player_id=pid, amount=amount, expires_at=expires) for pid in lucky])
    names = [engine.mask_name(u) for u in Player.objects.filter(id__in=lucky).values_list('username', flat=True)]
    shown = ', '.join(names[:12]) + (f' and {len(names) - 12} more' if len(names) > 12 else '')
    system_message(JetChatMessage.Kind.RAIN,
                   f'Rain! {len(lucky)} player{"s" if len(lucky) != 1 else ""} got a ${amount:.2f} free bet: {shown}')
    _publish({'type': 'rain'})
    return {'given': len(lucky), 'amount': str(amount), 'reason': None}


def maybe_auto_rain(now=None):
    """Called between rounds: rain when the schedule says it's time."""
    now = now or timezone.now()
    JetFreeBet.objects.filter(status=JetFreeBet.Status.AVAILABLE, expires_at__lte=now).update(status=JetFreeBet.Status.EXPIRED)
    cfg = JetSettings.load()
    if not (cfg.rain_enabled and cfg.chat_enabled and cfg.rain_every_minutes):
        return None
    if cfg.last_rain_at and now - cfg.last_rain_at < timedelta(minutes=cfg.rain_every_minutes):
        return None
    return rain(now=now)


def free_bets_for(player_id: int, now=None) -> list[dict]:
    now = now or timezone.now()
    rows = JetFreeBet.objects.filter(player_id=player_id, status=JetFreeBet.Status.AVAILABLE, expires_at__gt=now)
    return [{'id': f.id, 'amount': str(f.amount), 'expires_at': f.expires_at.isoformat()} for f in rows]
