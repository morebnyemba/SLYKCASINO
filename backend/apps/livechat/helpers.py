"""livechat orchestration helpers — facilitate services. NO model imports."""
from __future__ import annotations

from typing import Any

from common.idempotency import make_key


def get_cache_key_for_channel(channel: str) -> str:
    return make_key('livechat:channel', channel)


def validate_message_structure(payload: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    if not str(payload.get('body', '')).strip():
        errors.append('body is required')
    return errors
