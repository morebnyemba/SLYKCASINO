"""accounts orchestration helpers — facilitate the service layer.
NO model imports (keeps pure/orchestration logic acyclic with the ORM)."""
from __future__ import annotations

from typing import Any

from common.idempotency import make_key


def get_cache_key_for_player(player_id: int) -> str:
    return make_key('accounts:player', player_id)


def validate_player_payload(payload: dict[str, Any]) -> list[str]:
    """Structural validation only (no DB lookups). Returns a list of errors."""
    errors: list[str] = []
    if not str(payload.get('username', '')).strip():
        errors.append('username is required')
    email = str(payload.get('email', ''))
    if email and '@' not in email:
        errors.append('email is malformed')
    return errors
