"""promotions pure utilities — wagering math. NO model imports."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal('0.01')


def quantize(amount: Decimal | int | float | str) -> Decimal:
    return Decimal(str(amount)).quantize(CENTS, rounding=ROUND_HALF_UP)


def wagering_requirement(bonus_amount: Decimal, multiplier: Decimal) -> Decimal:
    """Total wagering needed to unlock a bonus = bonus * multiplier."""
    return quantize(Decimal(str(bonus_amount)) * Decimal(str(multiplier)))


def calculate_wagering_progress(progress: Decimal, required: Decimal) -> Decimal:
    """Completion percentage (0–100, 2dp). 0 required => fully complete."""
    required = Decimal(str(required))
    if required <= 0:
        return Decimal('100.00')
    pct = (Decimal(str(progress)) / required) * Decimal('100')
    capped = min(pct, Decimal('100'))
    return capped.quantize(CENTS, rounding=ROUND_HALF_UP)


def is_wagering_complete(progress: Decimal, required: Decimal) -> bool:
    return Decimal(str(progress)) >= Decimal(str(required))
