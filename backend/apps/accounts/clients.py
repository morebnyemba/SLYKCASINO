"""accounts external interfaces — normalize third-party (KYC) payloads into DTOs."""
from __future__ import annotations

from typing import Any

from .dtos import KycResultDTO


class KycProviderClient:
    """Interface to an external KYC/identity provider.

    The concrete HTTP call is intentionally left as a stub; the contract is that
    `verify` always returns a normalized :class:`KycResultDTO`, insulating the
    rest of the domain from provider-specific payload shapes.
    """

    provider_name = 'stub-kyc'

    def verify(self, player_id: int, document: dict[str, Any] | None = None) -> KycResultDTO:
        raw = self._call_provider(player_id, document or {})
        return self._normalize(player_id, raw)

    # -- internals ---------------------------------------------------------
    def _call_provider(self, player_id: int, document: dict[str, Any]) -> dict[str, Any]:
        # Replace with a real HTTP call. Stub returns a deterministic shape.
        return {'decision': 'approved', 'ref': f'kyc-{player_id}'}

    def _normalize(self, player_id: int, raw: dict[str, Any]) -> KycResultDTO:
        decision = raw.get('decision', 'pending')
        status = {'approved': 'verified', 'declined': 'unverified'}.get(decision, 'pending')
        return KycResultDTO(
            player_id=player_id,
            status=status,
            reference=str(raw.get('ref', '')),
            raw_provider=self.provider_name,
        )
