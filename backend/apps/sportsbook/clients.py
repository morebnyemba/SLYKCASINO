"""sportsbook external interfaces — normalize an odds-feed provider into DTOs."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class FeedMarket:
    external_id: str
    name: str
    odds: Decimal
    is_open: bool


class OddsFeedClient:
    """Interface to an external odds/results provider.

    `fetch_markets` returns normalized markets; `fetch_result` returns a settled
    outcome. Concrete HTTP omitted — the point is provider payloads are
    normalized here so services never see vendor-specific shapes.
    """

    provider_name = 'stub-odds'

    def fetch_markets(self) -> list[FeedMarket]:
        return [self._normalize(m) for m in self._call_markets()]

    def fetch_result(self, external_id: str) -> str:
        """Return 'won'|'lost'|'void'|'pending' for a market."""
        return self._call_result(external_id).get('outcome', 'pending')

    # -- internals ---------------------------------------------------------
    def _call_markets(self) -> list[dict[str, Any]]:
        return []

    def _call_result(self, external_id: str) -> dict[str, Any]:
        return {'outcome': 'pending'}

    def _normalize(self, raw: dict[str, Any]) -> FeedMarket:
        return FeedMarket(
            external_id=str(raw.get('id', '')),
            name=str(raw.get('name', '')),
            odds=Decimal(str(raw.get('odds', '1.95'))),
            is_open=bool(raw.get('open', True)),
        )
