"""Chat betting services: linking a chat address to an account, the chat PIN,
the daily chat staking cap, rate limiting and delivering replies."""
from __future__ import annotations

import logging
import secrets
import threading
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from django.contrib.auth.hashers import check_password, make_password
from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from .models import WHATSAPP, ChatbotSettings, ChatLink, ChatTicket, LinkCode

logger = logging.getLogger(__name__)

CODE_TTL = timedelta(minutes=10)
LINK_ATTEMPTS_PER_HOUR = 5
MESSAGES_PER_MINUTE = 20


class ChatError(ValueError):
    """A reason shown to the player in chat."""


# -- linking ------------------------------------------------------------------------

def new_link_code(player_id: int) -> LinkCode:
    """A fresh 6-digit code for a logged-in player (older unused ones die)."""
    now = timezone.now()
    LinkCode.objects.filter(player_id=player_id, used_at__isnull=True).update(used_at=now)
    return LinkCode.objects.create(player_id=player_id, code=f'{secrets.randbelow(10 ** 6):06d}', expires_at=now + CODE_TTL)


def _attempts_key(address: str) -> str:
    return f'chatbot:link-attempts:{address}'


@transaction.atomic
def link(address: str, code: str, *, channel: str = WHATSAPP) -> ChatLink:
    """Link `address` to the player who generated `code`. Five wrong codes an
    hour per address, so the 1-in-a-million code can't be guessed."""
    from django.core.cache import cache
    tries = cache.get(_attempts_key(address), 0)
    if tries >= LINK_ATTEMPTS_PER_HOUR:
        raise ChatError('Too many wrong codes. Try again in an hour.')
    now = timezone.now()
    row = (LinkCode.objects.select_for_update()
           .filter(code=code.strip(), used_at__isnull=True, expires_at__gt=now).order_by('-created_at').first())
    if row is None:
        cache.set(_attempts_key(address), tries + 1, 3600)
        raise ChatError('That code is wrong or has expired. Get a new one on the website: Account → WhatsApp betting.')
    row.used_at = now
    row.save(update_fields=['used_at'])
    # One number per player and one player per number: the new link replaces both.
    ChatLink.objects.filter(channel=channel, player_id=row.player_id).exclude(address=address).delete()
    existing = ChatLink.objects.filter(channel=channel, address=address).first()
    if existing and existing.player_id != row.player_id:
        existing.delete()
        existing = None
    if existing is None:
        try:
            existing = ChatLink.objects.create(channel=channel, address=address, player_id=row.player_id)
        except IntegrityError as exc:
            raise ChatError('Could not link right now, please try again.') from exc
    cache.delete(_attempts_key(address))
    from apps.accounts import services as accounts
    accounts.audit(row.player_id, 'chat_linked', None, channel=channel, number=f'…{address[-4:]}')
    return existing


def link_for(address: str, *, channel: str = WHATSAPP) -> Optional[ChatLink]:
    return ChatLink.objects.filter(channel=channel, address=address).first()


def unlink(player_id: int, *, channel: str = WHATSAPP, by: str = 'player') -> bool:
    deleted, _ = ChatLink.objects.filter(channel=channel, player_id=player_id).delete()
    if deleted:
        from apps.accounts import services as accounts
        accounts.audit(player_id, 'chat_unlinked', None, channel=channel, by=by)
    return bool(deleted)


# -- PIN and caps -------------------------------------------------------------------------

def set_pin(link: ChatLink, pin: str) -> None:
    pin = (pin or '').strip()
    if not (pin.isdigit() and 4 <= len(pin) <= 6):
        raise ChatError('A PIN is 4 to 6 digits.')
    link.pin_hash = make_password(pin)
    link.save(update_fields=['pin_hash'])


def clear_pin(link: ChatLink) -> None:
    link.pin_hash = ''
    link.save(update_fields=['pin_hash'])


def pin_ok(link: ChatLink, pin: str) -> bool:
    return bool(link.pin_hash) and check_password((pin or '').strip(), link.pin_hash)


def needs_pin(link: ChatLink, stake: Decimal) -> bool:
    """A PIN is asked for above the operator's threshold, and always when the
    player has set one."""
    return bool(link.pin_hash) or stake > ChatbotSettings.load().pin_above


def daily_cap(link: ChatLink) -> Decimal:
    operator = ChatbotSettings.load().daily_cap
    return min(operator, link.daily_cap) if link.daily_cap is not None else operator


def local_tz():
    """The players' time zone for chat (kick-off times, the daily limit's day)."""
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    from . import config
    try:
        return ZoneInfo(config.value('time_zone'))
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo('Africa/Harare')


def staked_today(player_id: int, *, channel: str = WHATSAPP) -> Decimal:
    tz = local_tz()
    start = timezone.make_aware(timezone.datetime.combine(timezone.localdate(timezone=tz), timezone.datetime.min.time()), tz)
    total = ChatTicket.objects.filter(channel=channel, player_id=player_id, created_at__gte=start).aggregate(t=Sum('stake'))['t']
    return (total or Decimal('0')).quantize(Decimal('0.01'))


def check_stake(link: ChatLink, stake: Decimal) -> None:
    cfg = ChatbotSettings.load()
    if stake > cfg.max_stake:
        raise ChatError(f'The most you can stake on one ticket through chat is ${cfg.max_stake:.2f}. Bet more on the website.')
    left = daily_cap(link) - staked_today(link.player_id, channel=link.channel)
    if stake > left:
        raise ChatError(f'That would pass your daily chat limit (${daily_cap(link):.2f}). '
                        f'You can still stake ${max(left, Decimal("0")):.2f} today through chat.')


# -- withdrawals -------------------------------------------------------------------------

def withdraw_destinations(player_id: int) -> list[tuple[str, str, str]]:
    """[(method, phone, label)]: the mobile-money numbers this player's paid
    deposits came from. A chat withdrawal may only go to one of these, so
    someone holding just the SIM can't send the money anywhere new."""
    from apps.wallet.models import PaymentTransaction, WithdrawalRequest
    labels = dict(WithdrawalRequest.Method.choices)
    mobile = ('ecocash', 'onemoney', 'innbucks')
    seen, out = set(), []
    for method, phone in (PaymentTransaction.objects.filter(player_id=player_id, status=PaymentTransaction.Status.PAID)
                          .exclude(phone='').order_by('-id').values_list('method', 'phone')):
        method = (method or '').lower()
        if method in mobile and (method, phone) not in seen:
            seen.add((method, phone))
            out.append((method, phone, labels.get(method, method.title())))
    return out[:5]


# -- rate limit ---------------------------------------------------------------------------

def over_rate(address: str) -> bool:
    """True once an address sends more than MESSAGES_PER_MINUTE in a minute."""
    from django.core.cache import cache
    key = f'chatbot:rate:{address}:{timezone.now():%Y%m%d%H%M}'
    try:
        n = cache.incr(key)
    except ValueError:
        cache.set(key, 1, 90)
        n = 1
    return n > MESSAGES_PER_MINUTE


# -- delivery -----------------------------------------------------------------------------

def record(address: str, reply: dict, *, channel: str = WHATSAPP, source: str = 'bot', by: str = ''):
    """Write the message to the delivery log (status: sending) before it's sent."""
    from .models import OutboundMessage
    return OutboundMessage.objects.create(channel=channel, address=address, text=reply['text'],
                                          buttons=[b if isinstance(b, str) else b[1] for b in reply.get('buttons') or [] if b]
                                          + ([f'☰ {reply["list"].get("button", "Choose")}'] if reply.get('list') else []),
                                          source=source, sent_by=by[:150])


def transmit(row, reply: dict) -> bool:
    """Send one logged message and write what happened to it onto its row."""
    from . import whatsapp
    if row.channel != WHATSAPP:
        result = whatsapp.SendResult(False, error='Unsupported channel.', code='channel')
    else:
        result = whatsapp.send(row.address, reply)
    row.provider_id = result.provider_id
    row.status = row.Status.SENT if result.ok else row.Status.FAILED
    row.error_code, row.error = result.code, result.error
    row.save(update_fields=['provider_id', 'status', 'error_code', 'error', 'updated_at'])
    return result.ok


def deliver(address: str, replies: list[dict], *, channel: str = WHATSAPP) -> None:
    """Log the replies now and send them, in order, once the transaction has
    committed. Sent straight from this process on a background thread: a reply
    never depends on a Celery worker being up (a task queued for a worker that
    isn't running is lost without a trace, and a chat must always answer)."""
    if not replies:
        return
    from .whatsapp import fit
    replies = fit(replies)
    rows = [record(address, r, channel=channel) for r in replies]

    def run():
        try:
            for row, reply in zip(rows, replies):
                transmit(row, reply)
        except Exception:  # noqa: BLE001
            logger.exception('chat delivery to …%s crashed', address[-4:])

    transaction.on_commit(lambda: threading.Thread(target=run, daemon=True).start())


def send_now(channel: str, address: str, replies: list[dict], *, source: str = 'bot', by: str = '') -> int:
    """Log and send replies now (for jobs that run later, and staff messages)."""
    from .whatsapp import fit
    sent = 0
    for reply in fit(replies):
        row = record(address, reply, channel=channel, source=source, by=by)
        if transmit(row, reply):
            sent += 1
    return sent


def acknowledge(provider_id: str) -> None:
    """Blue ticks and the "typing…" indicator for a message just received, on a
    background thread so the webhook still answers Meta immediately."""
    from . import whatsapp
    if whatsapp.configured():
        threading.Thread(target=whatsapp.mark_read, args=(provider_id,), daemon=True).start()


def apply_status(st) -> bool:
    """Record Meta's delivery report (sent, delivered, read, failed) for a message
    we sent. Reports can arrive out of order: a message never goes back from
    read to delivered."""
    from .models import OutboundMessage
    row = OutboundMessage.objects.filter(provider_id=st.provider_id).first()
    if row is None:
        return False
    order = {'queued': 0, 'sent': 1, 'delivered': 2, 'read': 3}
    if st.status == 'failed':
        row.status, row.error_code = OutboundMessage.Status.FAILED, st.code
        row.error = (st.error or 'Meta could not deliver this message.')[:400]
    elif order.get(st.status, 0) > order.get(row.status, -1) and row.status != OutboundMessage.Status.FAILED:
        row.status = st.status
    else:
        return False
    row.save(update_fields=['status', 'error_code', 'error', 'updated_at'])
    return True
