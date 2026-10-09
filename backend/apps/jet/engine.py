"""Jet maths — pure functions, no I/O, shared word for word with the player's
fairness checker.

Crash point (provably fair):
    digest = HMAC-SHA256(key=server_seed, msg="jet:<round id>")
    r      = first 52 bits of digest / 2^52                (uniform in [0, 1))
    crash  = floor(100 x (1 - edge) / (1 - r)) / 100, at least 1.00, at most the cap

This makes P(crash >= x) = (1 - edge) / x, so every cash-out strategy returns
(1 - edge) of the stake on average — the house edge is the only advantage.

Flight: the multiplier after t seconds is e^(RATE x t), so the server can decide
any cash-out from the round's start time alone, and the plane reaches the crash
point at t = ln(crash) / RATE.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import secrets
from decimal import ROUND_DOWN, Decimal

# Multiplier growth per second: 2x after ~6.9s, 10x after ~23s.
RATE = 0.10
CENT = Decimal('0.01')
ONE = Decimal('1.00')


def new_seed() -> str:
    return secrets.token_hex(32)


def seed_hash(seed: str) -> str:
    return hashlib.sha256(seed.encode()).hexdigest()


def crash_point(seed: str, round_id: int, house_edge_percent: Decimal, cap: Decimal) -> Decimal:
    digest = hmac.new(seed.encode(), f'jet:{round_id}'.encode(), hashlib.sha256).hexdigest()
    r = int(digest[:13], 16) / 2 ** 52
    keep = 1 - float(house_edge_percent) / 100
    raw = math.floor(100 * keep / (1 - r)) / 100
    value = Decimal(str(raw)).quantize(CENT, rounding=ROUND_DOWN)
    return max(ONE, min(value, Decimal(cap)))


def multiplier_at(seconds: float) -> Decimal:
    """Multiplier after `seconds` of flight, rounded down to the cent."""
    if seconds <= 0:
        return ONE
    return Decimal(str(math.exp(RATE * seconds))).quantize(CENT, rounding=ROUND_DOWN)


def seconds_to(multiplier: Decimal) -> float:
    """Flight time at which the multiplier reaches `multiplier`."""
    return math.log(float(multiplier)) / RATE if multiplier > 1 else 0.0


def payout_for(stake: Decimal, multiplier: Decimal, max_win: Decimal) -> Decimal:
    return min((Decimal(stake) * Decimal(multiplier)).quantize(CENT, rounding=ROUND_DOWN), Decimal(max_win))


def max_win_multiplier(stake: Decimal, max_win: Decimal) -> Decimal:
    """The multiplier at which a bet reaches the max win and is cashed out."""
    return (Decimal(max_win) / Decimal(stake)).quantize(CENT, rounding=ROUND_DOWN)


def mask_name(username: str) -> str:
    name = (username or 'player').strip()
    return f'{name[0]}***{name[-1]}' if len(name) > 2 else f'{name[0]}***'
