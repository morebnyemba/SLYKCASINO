"""livechat external interfaces — publish to the Erlang realtime engine."""
from __future__ import annotations

import logging
from urllib import error, request

from django.conf import settings

logger = logging.getLogger(__name__)


class RealtimePublisherClient:
    """Publishes messages to the Erlang/Cowboy WebSocket engine.

    Transport is an internal HTTP POST to the engine's /publish/<channel> ingest,
    which fans the body out to every socket on that channel. Disabled by default
    (REALTIME_PUBLISH_ENABLED) so dev/test never block on the network; when off
    it optimistically reports success, preserving the previous stub behaviour.
    `publish` returns whether the publish was accepted so callers can flip
    `delivered` and recovery can re-drive failures.
    """

    provider_name = 'erlang-ws'

    def publish(self, channel: str, body: str) -> bool:
        return self._call(channel, body)

    def _call(self, channel: str, body: str) -> bool:
        if not getattr(settings, 'REALTIME_PUBLISH_ENABLED', False):
            return True  # no-op transport in dev/test
        base = getattr(settings, 'REALTIME_PUBLISH_URL', 'http://erlang:8080/publish')
        url = f'{base.rstrip("/")}/{channel}'
        try:
            req = request.Request(
                url, data=body.encode('utf-8'), method='POST',
                headers={'Content-Type': 'text/plain; charset=utf-8'},
            )
            with request.urlopen(req, timeout=2) as resp:
                return 200 <= resp.status < 300
        except (error.URLError, OSError, ValueError):
            logger.warning('realtime publish failed for channel %s', channel, exc_info=True)
            return False
