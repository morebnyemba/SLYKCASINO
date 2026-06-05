"""sportsbook pure utilities — odds & payout math. NO model imports."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal('0.01')


def quantize(amount: Decimal | int | float | str) -> Decimal:
    return Decimal(str(amount)).quantize(CENTS, rounding=ROUND_HALF_UP)


def calculate_payout(stake: Decimal, odds: Decimal) -> Decimal:
    """Decimal-odds payout = stake * odds (includes stake)."""
    return quantize(Decimal(str(stake)) * Decimal(str(odds)))


def format_odds_decimal(odds: Decimal | float) -> str:
    """Render decimal odds to 2dp, e.g. 1.9 -> '1.90'."""
    return f'{Decimal(str(odds)).quantize(CENTS)}'


def implied_probability(odds: Decimal | float) -> Decimal:
    """1 / decimal_odds, as a 4dp probability."""
    o = Decimal(str(odds))
    if o <= 0:
        return Decimal('0')
    return (Decimal('1') / o).quantize(Decimal('0.0001'))
