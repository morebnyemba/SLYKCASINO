"""Base Pydantic DTO used for any data crossing an app boundary.

Domain apps subclass :class:`BaseDTO` in their ``dtos.py``. DTOs are the only
shapes that should travel between apps (service -> service) or in/out of
``clients.py`` — never raw Django model instances or querysets.
"""
from __future__ import annotations

from decimal import Decimal

from pydantic import BaseModel, ConfigDict


class BaseDTO(BaseModel):
    """Strict, immutable, ORM-friendly base for all boundary DTOs."""

    model_config = ConfigDict(
        frozen=True,            # DTOs are value objects — immutable
        extra='forbid',         # reject unknown provider fields explicitly
        from_attributes=True,   # allow DTO.model_validate(orm_instance)
        str_strip_whitespace=True,
    )


def money(value: Decimal | int | float | str) -> Decimal:
    """Coerce to a 2dp Decimal — the canonical monetary representation."""
    return Decimal(str(value)).quantize(Decimal('0.01'))
