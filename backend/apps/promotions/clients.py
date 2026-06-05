"""promotions external interfaces — normalize a CRM/campaign provider."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CampaignEligibility:
    eligible: bool
    reason: str = ''


class CampaignProviderClient:
    """Interface to an external CRM/eligibility provider.

    `check_eligibility` normalizes the provider's verdict so services need not
    know vendor payload shapes. Concrete transport omitted.
    """

    provider_name = 'stub-crm'

    def check_eligibility(self, player_id: int, promotion_id: int) -> CampaignEligibility:
        raw = self._call(player_id, promotion_id)
        return CampaignEligibility(
            eligible=bool(raw.get('eligible', True)),
            reason=str(raw.get('reason', '')),
        )

    def _call(self, player_id: int, promotion_id: int) -> dict[str, Any]:
        return {'eligible': True}
