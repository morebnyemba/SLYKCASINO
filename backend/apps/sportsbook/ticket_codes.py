"""Ticket codes: the random, unguessable reference printed on a ticket (and in
its barcode) that anyone holding the ticket can look it up by.

Ticket numbers (S12, M5) count up, so a public lookup by number would let anyone
page through everyone's bets; a code can't be guessed (31^10 ≈ 8×10^14).
"""
from __future__ import annotations

import secrets

# Same alphabet as booking codes: no 0/O or 1/I/L, so a code read out or typed is unambiguous.
ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
LENGTH = 10


def generate() -> str:
    return ''.join(secrets.choice(ALPHABET) for _ in range(LENGTH))


def unique_code() -> str:
    """A code no single or multiple has yet (singles and multiples share one lookup)."""
    from .models import Bet, BetSlip
    while True:
        code = generate()
        if not Bet.objects.filter(code=code).exists() and not BetSlip.objects.filter(code=code).exists():
            return code


def normalise(raw: str) -> str:
    """What a player typed or a scanner read: spaces and dashes dropped, upper case."""
    return ''.join(ch for ch in (raw or '').upper() if ch.isalnum())
