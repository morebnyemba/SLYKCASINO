"""Keeping the WhatsApp number in good standing (low ban risk).

Meta judges a business number on how people react to it (blocks and spam reports set its
quality rating) and on whether it follows the rules. What this module enforces on every
message the bot sends (services.transmit / send_now):

* **Only inside the 24-hour customer-service window.** A message the bot starts on its own
  (a ticket or deposit result, a staff reply) goes out only if the player wrote in the last
  24 hours; otherwise it's not attempted at all. No marketing broadcasts exist.
* **Paced.** Messages to one number are spaced (PAIR_GAP, avoids Meta's pair rate limit,
  error 131056) and the whole number is capped at PER_SECOND (avoids 130429).
* **Back off when Meta says slow down** (130429, 131056, 4, 80007): wait and retry twice.
* **Stop when Meta flags the number.** Spam rate limit (131048), a policy block (368) or a
  restricted account (131031) pause every message the bot would start on its own for a
  while, and staff see it on the health card. Replies to players who write keep working
  where Meta allows them.
* **Opt-out.** STOP unlinks the number; a number that sent STOP gets nothing it didn't ask for.

Meta's own requirements outside the code (gambling needs Meta's written approval, verified
business, approved display name) are listed on the WhatsApp bot page's health card.
"""
from __future__ import annotations

import logging
import time
from datetime import timedelta
from typing import Optional

from django.conf import settings
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

WINDOW = timedelta(hours=24) - timedelta(minutes=5)     # a small margin before Meta's 24 hours
PER_SECOND = 20
RETRY_CODES = {'130429', '131056', '4', '80007'}
RETRY_WAITS = (2.0, 6.0)
PAUSE_CODES = {
    '131048': (timedelta(hours=1), 'Meta’s spam rate limit: too many recent messages were blocked or reported.'),
    '368': (timedelta(hours=6), 'Meta temporarily blocked the number for a policy violation.'),
    '131031': (timedelta(hours=6), 'Meta locked or restricted the WhatsApp business account.'),
}
PAUSE_KEY = 'chatbot:guard:paused'


def pair_gap() -> float:
    return float(getattr(settings, 'CHATBOT_PAIR_GAP_SECONDS', 0.8))


def last_inbound(address: str, channel: str = 'whatsapp'):
    from .models import InboundMessage
    return (InboundMessage.objects.filter(channel=channel, address=address).order_by('-received_at')
            .values_list('received_at', flat=True).first())


def in_window(address: str, channel: str = 'whatsapp', *, now=None) -> bool:
    """Has this number written in the last 24 hours (so the business may message it)?"""
    last = last_inbound(address, channel)
    return bool(last and last >= (now or timezone.now()) - WINDOW)


def paused() -> Optional[dict]:
    """{'reason', 'until', 'code'} while Meta's flag pauses bot-initiated messages, else None."""
    return cache.get(PAUSE_KEY)


def note_error(code: str) -> None:
    """Meta flagged the number: pause what the bot starts on its own."""
    if code not in PAUSE_CODES:
        return
    span, reason = PAUSE_CODES[code]
    until = timezone.now() + span
    cache.set(PAUSE_KEY, {'reason': reason, 'until': until.isoformat(), 'code': code}, int(span.total_seconds()))
    logger.error('WhatsApp number flagged by Meta (%s): pausing bot-initiated messages until %s', code, until)


def clear_pause() -> None:
    cache.delete(PAUSE_KEY)


def throttle(address: str) -> None:
    """Space messages to one number and cap the whole number's rate (waits briefly when needed)."""
    gap = pair_gap()
    if gap > 0:
        key = f'chatbot:guard:last:{address}'
        last = cache.get(key)
        if last:
            wait = gap - (time.time() - last)
            if wait > 0:
                time.sleep(min(wait, gap))
        cache.set(key, time.time(), 60)
    for _ in range(20):                                  # global cap: at most PER_SECOND a second
        second = int(time.time())
        key = f'chatbot:guard:sec:{second}'
        cache.add(key, 0, 5)
        try:
            n = cache.incr(key)
        except ValueError:
            return
        if n <= PER_SECOND:
            return
        time.sleep(max(0.05, second + 1 - time.time()))


def status() -> dict:
    """For the admin health card: what the guard is doing and the checklist only Meta can tick."""
    p = paused()
    return {
        'paused': p,
        'window_hours': 24,
        'pair_gap_seconds': pair_gap(),
        'per_second': PER_SECOND,
        'checklist': [
            'Meta’s written approval for gambling on WhatsApp (required for betting businesses: apply through Meta’s '
            'regulated-industries form, licensed countries only).',
            'Business verification completed in Meta Business Manager.',
            'Display name approved (matches the website and brand).',
            'Business profile complete: description, website, email, address.',
            'Only message people who wrote first (the bot does this) and never buy or import number lists.',
            'Keep the quality rating Green: watch it here and pause anything that makes people block the number.',
        ],
    }
