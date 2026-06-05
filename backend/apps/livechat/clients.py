"""livechat external interfaces — publish to the Erlang realtime engine."""
from __future__ import annotations


class RealtimePublisherClient:
    """Publishes messages to the Erlang/Cowboy WebSocket engine.

    The concrete transport (HTTP push / Redis pub-sub bridge to the engine) is a
    stub; `publish` returns whether the publish was accepted so the service layer
    can flip `delivered` and recovery can re-drive failures.
    """

    provider_name = 'erlang-ws'

    def publish(self, channel: str, body: str) -> bool:
        return self._call(channel, body)

    def _call(self, channel: str, body: str) -> bool:
        # Replace with a real publish to /ws bridge. Stub reports success.
        return True
