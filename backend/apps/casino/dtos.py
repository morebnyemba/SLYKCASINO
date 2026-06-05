"""casino boundary DTOs (Pydantic)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from common.dtos import BaseDTO


class GameDTO(BaseDTO):
    id: int
    slug: str
    name: str
    provider: str
    rtp: Decimal
    is_active: bool


class SpinRequestDTO(BaseDTO):
    player_id: int
    game_id: int
    stake: Decimal


class RoundDTO(BaseDTO):
    id: int
    player_id: int
    game_id: int
    stake: Decimal
    win: Decimal
    status: str
    debit_confirmed: bool
    created_at: datetime
    settled_at: Optional[datetime] = None
