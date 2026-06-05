"""casino pure utilities — stake/RTP math. NO model imports."""
from __future__ import annotations

from decimal import ROUND_HALF_UP, Decimal

CENTS = Decimal('0.01')


def quantize(amount: Decimal | int | float | str) -> Decimal:
    return Decimal(str(amount)).quantize(CENTS, rounding=ROUND_HALF_UP)


def expected_return(stake: Decimal, rtp_percent: Decimal | float) -> Decimal:
    """Theoretical expected return for a stake at a game's RTP."""
    return quantize(Decimal(str(stake)) * Decimal(str(rtp_percent)) / Decimal('100'))


def net_result(stake: Decimal, win: Decimal) -> Decimal:
    """Player net for a round = win - stake (signed)."""
    return quantize(Decimal(str(win)) - Decimal(str(stake)))
