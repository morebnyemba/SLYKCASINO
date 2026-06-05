"""casino external interfaces — normalize a game-provider's payloads."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class RoundOutcome:
    provider_ref: str
    win: Decimal
    settled: bool


class CasinoProviderClient:
    """Interface to an external game/RGS provider.

    `open_round` reserves a round; `settle_round` returns the normalized outcome.
    Concrete transport omitted — normalization keeps provider payloads out of the
    domain.
    """

    provider_name = 'stub-rgs'

    def open_round(self, player_id: int, game_slug: str, stake: Decimal, idempotency_key: str) -> str:
        raw = self._call_open(player_id, game_slug, stake, idempotency_key)
        return str(raw.get('round_ref', idempotency_key))

    def settle_round(self, provider_ref: str) -> RoundOutcome:
        raw = self._call_settle(provider_ref)
        return RoundOutcome(
            provider_ref=provider_ref,
            win=Decimal(str(raw.get('win', '0'))),
            settled=bool(raw.get('settled', True)),
        )

    # -- internals ---------------------------------------------------------
    def _call_open(self, player_id: int, game_slug: str, stake: Decimal, key: str) -> dict[str, Any]:
        return {'round_ref': f'rgs-{key}'}

    def _call_settle(self, provider_ref: str) -> dict[str, Any]:
        return {'win': '0', 'settled': True}
