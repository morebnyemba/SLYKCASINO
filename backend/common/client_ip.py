"""The connecting device's IP behind our reverse proxy.

Clients can send their own X-Forwarded-For, so the leftmost entry is
attacker-controlled. Each trusted proxy appends the address it received the
request from, so the real client is the entry TRUSTED_PROXY_COUNT places from
the right (1 = our nginx only; 2 if another proxy such as Cloudflare or Nginx
Proxy Manager sits in front of it). DRF's throttles use the same count via
NUM_PROXIES, so rate limits and the audit log agree on who the client is.
"""
from __future__ import annotations

import ipaddress
from typing import Optional

from django.conf import settings


def _valid(ip: str) -> Optional[str]:
    try:
        return str(ipaddress.ip_address(ip.strip()))
    except ValueError:
        return None


def client_ip(request) -> Optional[str]:
    meta = request.META
    proxies = getattr(settings, 'TRUSTED_PROXY_COUNT', 1)
    if proxies > 0:
        hops = [h for h in meta.get('HTTP_X_FORWARDED_FOR', '').split(',') if h.strip()]
        if hops:
            # Fewer hops than trusted proxies: take the furthest one we have.
            return _valid(hops[-min(proxies, len(hops))])
    return _valid(meta.get('REMOTE_ADDR', ''))
