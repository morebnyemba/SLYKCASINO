"""Shared-secret auth for the Django <-> Erlang realtime engine boundary.

Both sides sign/verify with the same secret (Django's SECRET_KEY, passed to
the erlang container as REALTIME_SHARED_SECRET — see docker-compose*.yml), so
no separate credential needs provisioning. Used for two things:

1. Internal publish calls (Django -> erlang /publish) carry this secret in a
   header so the engine can tell a real Django call from anything else that
   can reach it on the docker network.
2. Admin WebSocket channels (admin:*) require a short-lived signed ticket —
   minted here for an authenticated admin, verified by the engine — so an
   arbitrary client can't join an operator-only channel.
"""
from __future__ import annotations

import hashlib
import hmac
import time

from django.conf import settings


def internal_token() -> str:
    """Secret presented to the realtime engine's /publish ingest."""
    return settings.SECRET_KEY


def make_ws_ticket(channel: str, ttl: int = 60) -> str:
    """Sign a one-time, time-boxed ticket admitting `channel` on /ws/."""
    expiry = int(time.time()) + ttl
    message = f'{channel}.{expiry}'.encode()
    signature = hmac.new(settings.SECRET_KEY.encode(), message, hashlib.sha256).hexdigest()
    return f'{channel}.{expiry}.{signature}'
