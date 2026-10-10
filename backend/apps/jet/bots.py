"""Simulated players for the Jet live bets list — display only.

Bots exist to make the round feel busy. They are never real money and never
touch anything that counts:

  * no Player, wallet, ledger entry or JetBet row is ever created for a bot,
    so GGR, NGR, takings, RTP, player counts, affiliate figures and every other
    report (all built from the ledger and JetBet) cannot include them;
  * they can't change a round — the crash point is fixed by the round's seed
    before betting opens, and bots only ever *read* it as the plane passes.

A round's bots are a pure function of (round id, settings), drawn from an HMAC
of the server secret, so the runner (which streams them live) and the state
endpoint (which snapshots them) always agree without storing anything.
Bot bet ids are negative so they can never collide with a real bet.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import random
from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from functools import lru_cache
from typing import Optional

from django.conf import settings as django_settings

from . import engine
from .models import JetRound, JetSettings

MAX_BOTS = 1000
# Bots join over the first part of the countdown, like people arriving.
JOIN_SPREAD = 0.85
# Stakes: log-normal around $1.50, so most bets are small change and big ones
# are rare (about 1 in 100 over $20, 1 in 1,500 over $50).
STAKE_MEDIAN = 1.5
STAKE_SPREAD = 1.1
NAME_CHARS = 'abcdefghijklmnopqrstuvwxyz'
NAME_ENDS = NAME_CHARS + '0123456789'


@dataclass(frozen=True)
class Bot:
    id: int
    name: str
    stake: Decimal
    join_after: float           # seconds after betting opens
    target: Optional[Decimal]   # cash-out multiplier; None rides to the crash


def _rng(round_id: int) -> random.Random:
    key = (django_settings.SECRET_KEY or 'jet').encode()
    digest = hmac.new(key, f'jet-bots:{round_id}'.encode(), hashlib.sha256).digest()
    return random.Random(int.from_bytes(digest, 'big'))


def _stake(rng: random.Random, lo: Decimal, hi: Decimal) -> Decimal:
    raw = rng.lognormvariate(math.log(STAKE_MEDIAN), STAKE_SPREAD)
    # People type round numbers more often than not.
    if raw >= 1 and rng.random() < 0.6:
        raw = round(raw) if raw < 20 else round(raw / 5) * 5
    value = Decimal(str(raw)).quantize(engine.CENT, rounding=ROUND_DOWN)
    return min(max(value, lo), hi)


def _target(rng: random.Random, cap: Decimal) -> Optional[Decimal]:
    if rng.random() < 0.04:
        return None  # the occasional rider who never cashes out
    # Heavy-tailed like real play: most leave under 2x, a few chase big numbers.
    raw = 0.98 / (1 - rng.random() * 0.985)
    value = Decimal(str(max(1.01, raw))).quantize(engine.CENT, rounding=ROUND_DOWN)
    return min(value, cap, Decimal('250'))


@lru_cache(maxsize=8)
def _plan(round_id: int, count: int, min_bet: Decimal, max_bet: Decimal, cap: Decimal, window: float) -> tuple[Bot, ...]:
    rng = _rng(round_id)
    n = round(count * rng.uniform(0.7, 1.0)) if count else 0
    lo, hi = max(min_bet, Decimal('0.10')), min(max_bet, Decimal('100'))
    bots = []
    for i in range(n):
        name = f'{rng.choice(NAME_CHARS)}***{rng.choice(NAME_ENDS)}'
        # Earlier arrivals are more common (a crowd that builds quickly).
        join = window * JOIN_SPREAD * (rng.random() ** 1.6)
        bots.append(Bot(id=-(round_id * MAX_BOTS + i + 1), name=name, stake=_stake(rng, lo, hi),
                        join_after=round(join, 2), target=_target(rng, cap)))
    return tuple(bots)


def plan(rnd: JetRound, cfg: Optional[JetSettings] = None) -> tuple[Bot, ...]:
    """Every bot that plays this round (empty when bots are off)."""
    cfg = cfg or JetSettings.load()
    if not cfg.bots_enabled or cfg.bot_count <= 0:
        return ()
    window = max(1.0, (rnd.betting_ends_at - rnd.created_at).total_seconds())
    return _plan(rnd.id, min(cfg.bot_count, MAX_BOTS), cfg.min_bet, cfg.max_bet, cfg.max_multiplier, window)


def _cashed_at(bot: Bot, reached: Decimal, cfg: JetSettings) -> Optional[Decimal]:
    """The multiplier this bot cashed out at, if the plane has passed its target."""
    if bot.target is None:
        return None
    target = min(bot.target, engine.max_win_multiplier(bot.stake, cfg.max_win))
    return target if target <= reached else None


def bet_payload(bot: Bot, rnd: JetRound, cashed: Optional[Decimal], cfg: JetSettings, lost: bool = False) -> dict:
    """Same shape as services.bet_payload, so the game draws bots like anyone else."""
    return {
        'id': bot.id, 'round': rnd.id, 'player': bot.name, 'slot': 1, 'stake': str(bot.stake),
        'status': 'cashed' if cashed else ('lost' if lost else 'active'),
        'cashout_multiplier': str(cashed) if cashed else None,
        'payout': str(engine.payout_for(bot.stake, cashed, cfg.max_win)) if cashed else '0',
    }


def reached(rnd: JetRound, now) -> Decimal:
    """How high the plane has got by `now` (the crash point once it crashed)."""
    if rnd.status == JetRound.Status.CRASHED:
        return rnd.crash_point
    if rnd.status != JetRound.Status.FLYING or rnd.started_at is None:
        return engine.ONE
    return min(engine.multiplier_at((now - rnd.started_at).total_seconds()), rnd.crash_point)


def snapshot(rnd: JetRound, now, cfg: Optional[JetSettings] = None) -> list[dict]:
    """The bots visible at `now`: joined so far, cashed out if the plane passed them."""
    cfg = cfg or JetSettings.load()
    bots = plan(rnd, cfg)
    if not bots:
        return []
    crashed = rnd.status == JetRound.Status.CRASHED
    if rnd.status == JetRound.Status.BETTING:
        elapsed = (now - rnd.created_at).total_seconds()
        return [bet_payload(b, rnd, None, cfg) for b in bots if b.join_after <= elapsed]
    top = reached(rnd, now)
    out = []
    for b in bots:
        cashed = _cashed_at(b, top, cfg)
        out.append(bet_payload(b, rnd, cashed, cfg, lost=crashed and not cashed))
    return out


def _compact(bot: Bot) -> list:
    return [bot.id, bot.name, str(bot.stake)]


class Feed:
    """Streams one round's bots to the live channel as they join and cash out.
    Used by the runner; every method is best-effort and never raises."""

    def __init__(self, rnd: JetRound):
        self.rnd = rnd
        self.cfg = JetSettings.load()
        try:
            # In arrival order, so "who has joined" is always a prefix.
            self.bots = tuple(sorted(plan(rnd, self.cfg), key=lambda b: b.join_after))
        except Exception:  # noqa: BLE001 — bots must never stop a round
            self.bots = ()
        self.joined = 0
        self.cashed: set[int] = set()

    def tick(self, now) -> None:
        if not self.bots:
            return
        from . import services
        try:
            if self.rnd.status == JetRound.Status.BETTING:
                elapsed = (now - self.rnd.created_at).total_seconds()
                new = [b for b in self.bots[self.joined:] if b.join_after <= elapsed]
                if new:
                    self.joined += len(new)
                    services.publish_now({'type': 'bots', 'round': self.rnd.id, 'bets': [_compact(b) for b in new]})
                return
            top = reached(self.rnd, now)
            out = []
            for b in self.bots:
                if b.id in self.cashed:
                    continue
                at = _cashed_at(b, top, self.cfg)
                if at:
                    self.cashed.add(b.id)
                    out.append([b.id, str(at), str(engine.payout_for(b.stake, at, self.cfg.max_win))])
            if out:
                services.publish_now({'type': 'bot_cashouts', 'round': self.rnd.id, 'bets': out})
        except Exception:  # noqa: BLE001
            pass

    def take_off(self, rnd: JetRound) -> None:
        """Flight started: make sure every bot has been announced."""
        self.rnd = rnd
        if not self.bots or self.joined >= len(self.bots):
            return
        from . import services
        rest = self.bots[self.joined:]
        self.joined = len(self.bots)
        services.publish_now({'type': 'bots', 'round': rnd.id, 'bets': [_compact(b) for b in rest]})
