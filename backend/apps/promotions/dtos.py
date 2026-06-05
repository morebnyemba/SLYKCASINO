"""promotions boundary DTOs (Pydantic)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from common.dtos import BaseDTO


class PromotionDTO(BaseDTO):
    id: int
    name: str
    kind: str
    active: bool
    bonus_amount: Decimal
    wagering_multiplier: Decimal


class ClaimDTO(BaseDTO):
    id: int
    player_id: int
    promotion_id: int
    bonus_amount: Decimal
    wagering_required: Decimal
    wagering_progress: Decimal
    status: str
    bonus_credited: bool
    created_at: datetime
    completed_at: Optional[datetime] = None
