"""livechat pure utilities — text formatting/sanitization. NO model imports."""
from __future__ import annotations

import re

_WHITESPACE = re.compile(r'\s+')
MAX_LEN = 500


def sanitize_message(body: str) -> str:
    """Collapse whitespace and hard-trim to the max length."""
    cleaned = _WHITESPACE.sub(' ', body).strip()
    return cleaned[:MAX_LEN]


def is_valid_channel(channel: str) -> bool:
    """Channels are lowercase tokens, optionally namespaced with ':'."""
    return bool(re.fullmatch(r'[a-z0-9_]+(:[a-z0-9_]+)?', channel or ''))
