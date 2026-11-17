"""Reprice deposit commissions (CPA) to a lower % of the customer's first deposit.

The operator moved every agent's deposit commission to `percent` (10%). This
brings commissions already earned under higher rates down to the same terms:
each live CPA commission paying more than `percent` of the customer's first
deposit (capped by the agent's own cap; any flat amount dropped) is cut to it.
Eligibility is not re-judged — a commission that was earned stays earned, only
its size changes (so this never undoes `restore_cpa`).

The excess comes back exactly as the audit's does (`clawback._apply`): pending
commissions are just corrected; approved/paid ones are recovered from the
agent's unpaid balance, then their Winnings wallet, and anything left nets off
future commissions; the operating pool is credited. Dry run unless `apply`.
Idempotent: a second run finds nothing above the rate.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db import transaction

from . import clawback, utils
from .models import Affiliate, AffiliateProgramme, Commission

ZERO = Decimal('0.00')
REPRICE_NOTE = 'CPA repriced'
DEFAULT_PERCENT = Decimal('10')


def target_for(c: Commission, affiliate: Affiliate, percent: Decimal) -> Decimal:
    """What the commission pays at `percent` of the first deposit (never more than it paid)."""
    first = c.base_amount or ZERO
    if first <= 0:
        return c.amount
    return min(utils.deposit_commission(first, ZERO, percent, affiliate.cpa_cap), c.amount)


def _rows(affiliate: Affiliate, percent: Decimal) -> list[clawback.Row]:
    rows = []
    for c in (affiliate.commissions.filter(kind=Commission.Kind.CPA)
              .exclude(status=Commission.Status.REJECTED).select_related('referral')):
        target = target_for(c, affiliate, percent)
        if c.amount - target < Decimal('0.01'):
            continue
        rows.append(clawback.Row(
            commission_id=c.id, affiliate_id=affiliate.id, affiliate_code=affiliate.code,
            player_id=c.referral.player_id if c.referral else None, status=c.status, created_at=c.created_at,
            first_deposit=c.base_amount, deposits=ZERO, real_turnover=ZERO, paid=c.amount, correct=target,
            reason=f'deposit commission is now {percent.normalize():f}% of the first deposit', waived=False,
        ))
    return rows


def set_terms(percent: Decimal) -> int:
    """Every agent, and the default for new agents, on `percent` deposit
    commission with no flat amount. Returns how many agents changed."""
    from django.db.models import Q
    AffiliateProgramme.load()
    AffiliateProgramme.objects.filter(pk=1).update(default_cpa_percent=percent, default_cpa_amount=ZERO)
    return (Affiliate.objects.filter(~Q(cpa_percent=percent) | ~Q(cpa_amount=ZERO))
            .update(cpa_percent=percent, cpa_amount=ZERO))


def run(*, percent: Decimal = DEFAULT_PERCENT, affiliate_ids: Optional[list[int]] = None, apply: bool = False,
        by: str = '') -> list[clawback.AffiliateResult]:
    """Review (and with `apply`, cut) CPA commissions above `percent` of the first
    deposit. Each agent in its own transaction, under its row lock."""
    qs = Affiliate.objects.filter(commissions__kind=Commission.Kind.CPA).distinct().order_by('pk')
    if affiliate_ids:
        qs = qs.filter(pk__in=affiliate_ids)
    pct = f'{percent.normalize():f}%'
    results = []
    for aid in qs.values_list('pk', flat=True):
        with transaction.atomic():
            affiliate = Affiliate.objects.select_for_update().get(pk=aid)
            rows = _rows(affiliate, percent)
            if not rows:
                continue
            result = clawback.AffiliateResult(affiliate_id=affiliate.id, code=affiliate.code, rows=rows)
            if apply:
                fix = clawback.AffiliateResult(affiliate_id=affiliate.id, code=affiliate.code, rows=rows)
                clawback._apply(affiliate, rows, fix, by=by, label=REPRICE_NOTE, notify=(
                    f'Deposit commission is now {pct}',
                    f'Deposit commissions are now {pct} of each customer’s first deposit. Commissions paid at a higher '
                    'rate were brought down to it: {excess} was taken back. Open your agent dashboard for the details.'))
                Commission.objects.filter(pk__in=[r.commission_id for r in fix.rows]).update(rate=percent)
                result.rows = fix.rows
                result.from_balance, result.from_wallet, result.carried = fix.from_balance, fix.from_wallet, fix.carried
                result.reversed = fix.excess
            results.append(result)
    return results
