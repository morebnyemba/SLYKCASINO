"""Simulated players chatting in the lobby — light, neutral background chatter.

Guardrails (each enforced here and covered by tests):
  1. Lines come only from the fixed lists below: greetings and reactions to the
     round. Bots never claim wins, deposits or balances of their own and never
     tell anyone to bet, deposit, chase losses or "go bigger".
  2. Bots never address or name a real player — no line contains a name.
  3. Light volume: at most `bot_chat_per_minute` lines (capped at MAX_PER_MINUTE).
  4. Real chat comes first: bots hold back while real players are talking.
  5. Bot lines are stored as kind "bot" (never with a player id), so the admin
     moderation list labels them as simulated, and the game rules disclose them.
"""
from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from django.utils import timezone

from . import bots
from .models import JetChatMessage, JetRound, JetSettings

MAX_PER_MINUTE = 10
# Real players talking in this window make bots quieter or silent.
REAL_CHAT_WINDOW = timedelta(minutes=2)
REAL_CHAT_SILENCES = 3
# Bot lines older than this are deleted (they're only background).
KEEP_FOR = timedelta(hours=6)

GREETINGS = (
    'gl all', 'good luck everyone', 'hi all', 'evening all 👋', 'hello pilots', 'gl 🍀', 'here we go',
    'let’s see this one', 'come on plane ✈️', 'back again 😄', 'morning all', 'gl gl',
)
LOW = (  # flew away early
    'ouch', 'that was quick', 'early one 😅', 'gone already', 'blink and you miss it', 'unlucky round',
    'wow that was fast', 'oof',
)
MID = (
    'nice round', 'gg', 'not bad', 'smooth one', 'ok that was decent', 'gg all', 'nice', 'solid round',
)
HIGH = (  # flew a long way
    'that flew 😮', 'what a round', 'big one!', '🔥🔥', 'wow look at it go', 'huge round', 'it just kept going',
    'sky high ✈️', 'that was a long flight',
)
ALL_LINES = GREETINGS + LOW + MID + HIGH


def _pool(phase: str, rnd: JetRound) -> tuple[str, ...]:
    if phase != 'crashed':
        return GREETINGS
    if rnd.crash_point < Decimal('1.5'):
        return LOW
    if rnd.crash_point >= Decimal('10'):
        return HIGH
    return MID


def _real_chatter(now) -> int:
    return JetChatMessage.objects.filter(
        kind=JetChatMessage.Kind.CHAT, hidden=False, created_at__gte=now - REAL_CHAT_WINDOW,
    ).count()


def lines_due(cfg: JetSettings, seconds: float, real: int) -> float:
    """Expected bot lines for a stretch of `seconds`, after the real-chat brake."""
    if real >= REAL_CHAT_SILENCES:
        return 0.0
    rate = min(cfg.bot_chat_per_minute, MAX_PER_MINUTE) / 60.0
    if real:
        rate /= 2 * real
    return rate * seconds


def speak(rnd: JetRound, phase: str, seconds: float, *, now=None, rng: Optional[random.Random] = None) -> list[JetChatMessage]:
    """Post this stretch's bot lines (`phase` is 'betting' or 'crashed';
    `seconds` is how long since bots last had the chance to speak)."""
    from .social import _publish, message_payload
    now = now or timezone.now()
    cfg = JetSettings.load()
    if not (cfg.chat_enabled and cfg.bots_enabled and cfg.bot_chat_enabled and cfg.bot_chat_per_minute):
        return []
    plan = bots.plan(rnd, cfg)
    if not plan:
        return []
    rng = rng or random.Random()
    expected = lines_due(cfg, seconds, _real_chatter(now))
    count = int(expected) + (1 if rng.random() < expected - int(expected) else 0)
    pool = _pool(phase, rnd)
    said = []
    for bot in rng.sample(plan, min(count, len(plan))):
        msg = JetChatMessage.objects.create(kind=JetChatMessage.Kind.BOT, name=bot.name, body=rng.choice(pool))
        _publish({'type': 'chat', 'message': message_payload(msg)})
        said.append(msg)
    return said


def prune(now=None) -> int:
    now = now or timezone.now()
    return JetChatMessage.objects.filter(kind=JetChatMessage.Kind.BOT, created_at__lt=now - KEEP_FOR).delete()[0]
