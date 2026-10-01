"""casino orchestration helpers — facilitate services. NO model imports."""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from common.idempotency import make_key


def get_cache_key_for_game(game_id: int) -> str:
    return make_key('casino:game', game_id)


def round_debit_key(round_id: int) -> str:
    """Deterministic wallet key for a round's stake debit."""
    return make_key('wallet:casino', round_id, 'debit')


def round_credit_key(round_id: int) -> str:
    return make_key('wallet:casino', round_id, 'credit')


def crash_debit_key(crash_id: int) -> str:
    """Deterministic wallet key for a crash bet's stake debit."""
    return make_key('wallet:crash', crash_id, 'debit')


def crash_credit_key(crash_id: int) -> str:
    return make_key('wallet:crash', crash_id, 'credit')


def validate_spin_request_structure(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not payload.get('game_id'):
        errors.append('game_id is required')
    try:
        if Decimal(str(payload.get('stake'))) <= 0:
            errors.append('stake must be positive')
    except Exception:  # noqa: BLE001
        errors.append('stake is malformed')
    return errors
