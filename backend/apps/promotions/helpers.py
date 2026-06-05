"""promotions orchestration helpers — facilitate services. NO model imports."""
from __future__ import annotations

from typing import Any

from common.idempotency import make_key


def get_cache_key_for_claim(claim_id: int) -> str:
    return make_key('promotions:claim', claim_id)


def bonus_credit_key(claim_id: int) -> str:
    """Deterministic wallet key for crediting a claim's bonus."""
    return make_key('wallet:promo', claim_id, 'bonus')


def validate_claim_request_structure(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not payload.get('promotion_id'):
        errors.append('promotion_id is required')
    if not payload.get('player_id'):
        errors.append('player_id is required')
    return errors
