"""Encryption for the WhatsApp secrets kept in the database (access token, app
secret, verify token), so a database dump or backup doesn't hand out a working
token.

The key comes from CHATBOT_SECRET_KEY when set (best: it lives only in
.env.prod, apart from the database), else it's derived from DJANGO_SECRET_KEY.
If the key changes, stored secrets can no longer be read: they count as unset
(the .env.prod value applies, if any) and the admin page asks for them again.
"""
from __future__ import annotations

import base64
import hashlib
from typing import Optional

from django.conf import settings


def _fernet():
    from cryptography.fernet import Fernet
    raw = (getattr(settings, 'CHATBOT_SECRET_KEY', '') or settings.SECRET_KEY).encode()
    key = base64.urlsafe_b64encode(hashlib.sha256(b'chatbot-secrets:' + raw).digest())
    return Fernet(key)


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode()).decode() if value else ''


def decrypt(token: str) -> Optional[str]:
    """The secret, '' when none is stored, or None when it can't be read (the key changed)."""
    if not token:
        return ''
    from cryptography.fernet import InvalidToken
    try:
        return _fernet().decrypt(token.encode()).decode()
    except (InvalidToken, ValueError):
        return None


def hint(value: str) -> str:
    """Enough to recognise a secret without revealing it: its last four characters."""
    return f'…{value[-4:]}' if value and len(value) >= 8 else ('set' if value else '')
