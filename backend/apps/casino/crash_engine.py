"""Provably-fair crash math — pure functions, no I/O.

The crash point is derived from a secret `server_seed` (committed via its SHA-256
hash before the round, revealed after) using the well-known "bustabit" integer
formula, which yields a ~1% house edge. The live multiplier is a deterministic
exponential function of elapsed time, so the server can authoritatively decide a
cash-out from the round's start timestamp alone.
"""
from __future__ import annotations

import hashlib
import hmac
import math
import secrets
from decimal import ROUND_DOWN, Decimal

# Growth rate of the live multiplier, per second: multiplier(t) = e^(RATE * t).
# Shared verbatim with the web client (apps/web .../casino/crash) so the on-screen
# curve matches the server's authoritative cash-out calculation.
CRASH_GROWTH_RATE = 0.15

# 1-in-N rounds bust instantly at 1.00x — this is the house edge (~1%).
_INSTANT_BUST_ODDS = 101
_CENTS = Decimal('0.01')


def new_server_seed() -> str:
    """A fresh 32-byte secret as hex."""
    return secrets.token_hex(32)


def seed_hash(server_seed: str) -> str:
    """The public commitment shown before the round."""
    return hashlib.sha256(server_seed.encode()).hexdigest()


def crash_point(server_seed: str, nonce: int) -> Decimal:
    """Derive the crash multiplier (>= 1.00) for a (seed, nonce) pair."""
    digest = hmac.new(server_seed.encode(), str(nonce).encode(), hashlib.sha256).hexdigest()
    h = int(digest[:13], 16)  # 52 bits of entropy
    if h % _INSTANT_BUST_ODDS == 0:
        return Decimal('1.00')
    e = 2 ** 52
    points = (100 * e - h) // (e - h)  # integer hundredths, >= 100
    return (Decimal(points) / 100).quantize(_CENTS, rounding=ROUND_DOWN)


def multiplier_at(elapsed_seconds: float) -> Decimal:
    """Live multiplier after `elapsed_seconds`, rounded down to the cent."""
    if elapsed_seconds <= 0:
        return Decimal('1.00')
    value = Decimal(str(math.exp(CRASH_GROWTH_RATE * elapsed_seconds)))
    return value.quantize(_CENTS, rounding=ROUND_DOWN)
