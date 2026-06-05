"""Deterministic idempotency-key helpers.

A stable key for a logical operation lets ledger writes and provider calls be
retried safely: the second attempt collides on a unique constraint / get_or_create
and becomes a no-op. Keys are intentionally human-readable for debuggability.

This module is pure (no Django/model imports) and may be used from any layer.
"""
from __future__ import annotations

import hashlib


def make_key(namespace: str, *parts: object) -> str:
    """Build a deterministic key like ``wallet:debit:bet:42``.

    The same inputs always yield the same key, so callers can recompute it on
    retry without persisting it.
    """
    tail = ':'.join(str(p) for p in parts)
    return f'{namespace}:{tail}' if tail else namespace


def digest_key(namespace: str, *parts: object) -> str:
    """A fixed-length hashed variant for when parts are large/sensitive."""
    raw = make_key(namespace, *parts).encode('utf-8')
    return f'{namespace}:{hashlib.sha256(raw).hexdigest()[:32]}'
