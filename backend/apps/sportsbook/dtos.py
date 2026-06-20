"""sportsbook boundary DTOs (Pydantic)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import List, Optional

from common.dtos import BaseDTO


class BetRequestDTO(BaseDTO):
    """Inbound bet placement request (validated before it crosses into services)."""
    player_id: Optional[int] = None
    event: str
    event_id: Optional[int] = None
    selection: str = 'home'
    stake: Decimal
    odds: Decimal


class BetDTO(BaseDTO):
    id: int
    player_id: Optional[int] = None
    event: str
    selection: str = 'home'
    stake: Decimal
    odds: Decimal
    status: str
    payout: Decimal = Decimal('0')
    placed_at: datetime
    settled_at: Optional[datetime] = None


class AccumulatorLegDTO(BaseDTO):
    """One leg of an inbound accumulator request."""
    event: str
    event_id: Optional[int] = None
    selection: str = 'home'
    odds: Decimal


class AccumulatorRequestDTO(BaseDTO):
    """Inbound accumulator placement request."""
    player_id: Optional[int] = None
    stake: Decimal
    legs: List[AccumulatorLegDTO]
