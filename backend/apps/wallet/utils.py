"""wallet pure utilities — performance-critical money math. NO model imports."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable

CENTS = Decimal('0.01')


def quantize(amount: Decimal | int | float | str) -> Decimal:
    """Canonical 2dp rounding for money."""
    return Decimal(str(amount)).quantize(CENTS, rounding=ROUND_HALF_UP)


def sum_entries(amounts: Iterable[Decimal]) -> Decimal:
    """Authoritative balance = sum of signed ledger amounts."""
    total = Decimal('0')
    for a in amounts:
        total += a
    return quantize(total)


def to_debit(amount: Decimal) -> Decimal:
    """Normalize a positive magnitude to a signed debit (negative)."""
    return -quantize(abs(amount))


def to_credit(amount: Decimal) -> Decimal:
    """Normalize a positive magnitude to a signed credit (positive)."""
    return quantize(abs(amount))


def has_sufficient_funds(balance: Decimal, debit_magnitude: Decimal) -> bool:
    return quantize(balance) >= quantize(abs(debit_magnitude))


def format_money(amount: Decimal, currency: str = 'USD') -> str:
    return f'{quantize(amount)} {currency}'
