"""accounts pure utilities — stateless, NO model/Django imports."""
from __future__ import annotations

import re

_USERNAME_RE = re.compile(r'[^a-z0-9_]+')


def normalize_username(raw: str) -> str:
    """Lowercase, trim, collapse illegal chars to underscores."""
    return _USERNAME_RE.sub('_', raw.strip().lower()).strip('_')


def mask_email(email: str) -> str:
    """`john.doe@x.com` -> `j***e@x.com` for safe display/logging."""
    if '@' not in email:
        return email
    local, _, domain = email.partition('@')
    if len(local) <= 2:
        masked = local[:1] + '*'
    else:
        masked = f'{local[0]}***{local[-1]}'
    return f'{masked}@{domain}'


def is_valid_kyc_transition(current: str, nxt: str) -> bool:
    """Pure rule: KYC may only move forward, never back to unverified."""
    order = {'unverified': 0, 'pending': 1, 'verified': 2}
    return order.get(nxt, -1) >= order.get(current, 0)
