"""accounts boundary DTOs (Pydantic)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from common.dtos import BaseDTO


class PlayerDTO(BaseDTO):
    id: int
    username: str
    email: str = ''
    kyc_status: str
    created_at: Optional[datetime] = None


class KycResultDTO(BaseDTO):
    """Normalized result returned by an external KYC provider."""
    player_id: int
    status: str            # one of Player.Kyc values
    reference: str = ''
    raw_provider: str = ''
