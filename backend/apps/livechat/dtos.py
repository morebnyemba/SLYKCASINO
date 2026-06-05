"""livechat boundary DTOs (Pydantic)."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from common.dtos import BaseDTO


class ChatMessageDTO(BaseDTO):
    id: int
    channel: str
    player_id: Optional[int] = None
    body: str
    delivered: bool
    created_at: datetime


class PostMessageDTO(BaseDTO):
    channel: str = 'lobby'
    player_id: Optional[int] = None
    body: str
