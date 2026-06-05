"""sportsbook boundary DTOs (Pydantic)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from common.dtos import BaseDTO


class BetRequestDTO(BaseDTO):
    """Inbound bet placement request (validated before it crosses into services)."""
    player_id: Optional[int] = None
    event: str
    stake: Decimal
    odds: Decimal


class BetDTO(BaseDTO):
    id: int
    player_id: Optional[int] = None
    event: str
    stake: Decimal
    odds: Decimal
    status: str
    payout: Decimal = Decimal('0')
    placed_at: datetime
    settled_at: Optional[datetime] = None
