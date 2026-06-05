"""wallet orchestration helpers — facilitate services. NO model imports."""
from __future__ import annotations

from typing import Any

from common.idempotency import make_key


def get_cache_key_for_balance(player_id: int) -> str:
    return make_key('wallet:balance', player_id)


def build_idempotency_key(domain: str, *parts: object) -> str:
    """Stable key for a ledger movement, e.g. ('bet', 42, 'stake')."""
    return make_key(f'wallet:{domain}', *parts)


def validate_post_request_structure(payload: dict[str, Any]) -> list[str]:
    """Pure structural validation of a post-entry request (no DB)."""
    errors: list[str] = []
    if payload.get('idempotency_key') in (None, ''):
        errors.append('idempotency_key is required')
    if payload.get('kind') in (None, ''):
        errors.append('kind is required')
    if payload.get('amount') in (None, ''):
        errors.append('amount is required')
    return errors
