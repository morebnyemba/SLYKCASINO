"""sportsbook orchestration helpers — facilitate services. NO model imports."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from common.idempotency import make_key


def get_cache_key_for_event(event_id: int | str) -> str:
    return make_key('sportsbook:event', event_id)


def stake_idempotency_key(bet_id: int) -> str:
    """Deterministic key for a bet's stake debit — lets recovery re-drive safely."""
    return make_key('wallet:bet', bet_id, 'stake')


def payout_idempotency_key(bet_id: int) -> str:
    return make_key('wallet:bet', bet_id, 'payout')


def validate_bet_request_structure(payload: dict[str, Any]) -> list[str]:
    """Pure structural validation of a bet request (no DB)."""
    errors: list[str] = []
    if not str(payload.get('event', '')).strip():
        errors.append('event is required')
    try:
        if Decimal(str(payload.get('stake'))) <= 0:
            errors.append('stake must be positive')
    except Exception:  # noqa: BLE001
        errors.append('stake is malformed')
    try:
        if Decimal(str(payload.get('odds'))) < 1:
            errors.append('odds must be >= 1.0')
    except Exception:  # noqa: BLE001
        errors.append('odds is malformed')
    return errors
