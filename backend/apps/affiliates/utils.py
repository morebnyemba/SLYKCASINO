"""affiliates pure functions — NO model imports."""
from __future__ import annotations

from datetime import date
from decimal import ROUND_DOWN, Decimal

# Ledger kinds that make up gaming activity: stakes are negative, wins positive.
GAMING_KINDS = ('bet_stake', 'bet_payout', 'casino_debit', 'casino_credit')
CENT = Decimal('0.01')


def net_gaming_revenue(totals: dict[str, Decimal]) -> Decimal:
    """Operator revenue from one player's ledger totals: what they lost
    (stakes minus winnings and refunds) less the bonuses they were given."""
    gross = -sum((totals.get(k, Decimal('0')) for k in GAMING_KINDS), Decimal('0'))
    return gross - totals.get('bonus', Decimal('0'))


def commission_for(ngr: Decimal, percent: Decimal) -> Decimal:
    """Revenue share on a positive month; a losing month pays nothing (no
    negative carry-over). Rounded down to the cent."""
    if ngr <= 0 or percent <= 0:
        return Decimal('0.00')
    return (ngr * percent / Decimal('100')).quantize(CENT, rounding=ROUND_DOWN)


def month_start(day: date) -> date:
    return day.replace(day=1)


def next_month(day: date) -> date:
    return date(day.year + (day.month == 12), day.month % 12 + 1, 1)


def previous_month(day: date) -> date:
    first = month_start(day)
    return date(first.year - (first.month == 1), (first.month - 2) % 12 + 1, 1)


def mask_username(name: str) -> str:
    """Show affiliates enough to recognise a referral, not their full identity."""
    if len(name) <= 2:
        return name[:1] + '*'
    return name[:2] + '*' * min(len(name) - 2, 5)


def deposit_commission(first_deposit: Decimal, flat: Decimal, percent: Decimal, cap: Decimal) -> Decimal:
    """One-off commission for a qualifying referral: the flat CPA plus `percent`
    of their first deposit, the percentage part capped at `cap` (0 = no cap).
    Rounded down to the cent."""
    part = Decimal('0')
    if percent > 0 and first_deposit > 0:
        part = first_deposit * percent / Decimal('100')
        if cap > 0:
            part = min(part, cap)
    total = (flat if flat > 0 else Decimal('0')) + part
    return total.quantize(CENT, rounding=ROUND_DOWN)


def welcome_bonus(first_deposit: Decimal, percent: Decimal, cap: Decimal, min_deposit: Decimal) -> Decimal:
    """A referred player's bonus on their first deposit (0 if under the minimum)."""
    if percent <= 0 or first_deposit <= 0 or first_deposit < min_deposit:
        return Decimal('0.00')
    bonus = first_deposit * percent / Decimal('100')
    if cap > 0:
        bonus = min(bonus, cap)
    return bonus.quantize(CENT, rounding=ROUND_DOWN)


def carry(ngr: Decimal, carried_in: Decimal, carryover: bool) -> tuple[Decimal, Decimal]:
    """(amount the revenue share is computed on, balance carried to next month).
    With carry-over a losing month's deficit is netted against later months
    until earned back; without it every month starts from zero."""
    if not carryover:
        return ngr, Decimal('0')
    net = ngr + min(carried_in, Decimal('0'))
    return net, min(net, Decimal('0'))
