"""wallet boundary DTOs (Pydantic)."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from common.dtos import BaseDTO


class BalanceDTO(BaseDTO):
    player_id: int
    balance: Decimal
    currency: str


class LedgerEntryDTO(BaseDTO):
    id: int
    amount: Decimal
    kind: str
    reference: str = ''
    idempotency_key: str
    created_at: datetime


class PostEntryDTO(BaseDTO):
    """Inbound request to post a single ledger movement."""
    player_id: int
    amount: Decimal            # signed
    kind: str
    idempotency_key: str
    reference: str = ''
