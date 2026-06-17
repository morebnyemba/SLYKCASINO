"""casino external interfaces — normalize a game-provider's payloads."""
from __future__ import annotations

import random
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

    Stub simulates plausible slot outcomes (~96% RTP over many spins).
    Tiers: no-win 50%, break-even 30%, 2× 15%, 5× 4%, 20× 1%.
    """

    provider_name = 'stub-rgs'

    def open_round(self, player_id: int, game_slug: str, stake: Decimal, idempotency_key: str) -> str:
        raw = self._call_open(player_id, game_slug, stake, idempotency_key)
        return str(raw.get('round_ref', idempotency_key))

    def settle_round(self, provider_ref: str, stake: Decimal = Decimal('0')) -> RoundOutcome:
        raw = self._call_settle(provider_ref, stake)
        return RoundOutcome(
            provider_ref=provider_ref,
            win=Decimal(str(raw.get('win', '0'))),
            settled=bool(raw.get('settled', True)),
        )

    # -- internals ---------------------------------------------------------
    def _call_open(self, player_id: int, game_slug: str, stake: Decimal, key: str) -> dict[str, Any]:
        return {'round_ref': f'rgs-{key}'}

    def _call_settle(self, provider_ref: str, stake: Decimal = Decimal('0')) -> dict[str, Any]:
        r = random.random()
        if r < 0.50:
            multiplier = Decimal('0')       # no win
        elif r < 0.80:
            multiplier = Decimal('1')       # break even
        elif r < 0.95:
            multiplier = Decimal('2')       # 2×
        elif r < 0.99:
            multiplier = Decimal('5')       # 5×
        else:
            multiplier = Decimal('20')      # jackpot
        return {'win': str(stake * multiplier), 'settled': True}

