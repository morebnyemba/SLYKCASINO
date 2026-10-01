"""affiliates orchestration helpers — NO model imports."""
from __future__ import annotations

import re
import secrets

from common.idempotency import make_key

_CODE_RE = re.compile(r'^[A-Z0-9]{3,24}$')


def normalize_code(code: str) -> str:
    return re.sub(r'[^A-Za-z0-9]', '', code or '').upper()[:24]


def is_valid_code(code: str) -> bool:
    return bool(_CODE_RE.match(code))


def suggested_code(username: str) -> str:
    """Readable default: up to 6 letters of the username plus 4 random chars."""
    stem = normalize_code(username)[:6] or 'BLITS'
    return f'{stem}{secrets.token_hex(2).upper()}'


def commission_payout_key(commission_id: int) -> str:
    """Deterministic key for a commission's wallet credit — recovery re-drives it safely."""
    return make_key('wallet:affiliate', commission_id, 'payout')
