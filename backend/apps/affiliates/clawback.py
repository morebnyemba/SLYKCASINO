"""Reverse deposit commissions (CPA) that should never have been paid.

Before the CPA rules were tightened (real-money play-through only, 3x the first
deposit, no accounts linked to the agent), a referral could qualify on bonus
money: deposit 1.00, receive bonus money, stake it, and the agent earned the
full CPA, including any flat amount, worth many times the deposit.

`run()` re-checks every CPA commission ever created against the current rules
(the same `_cpa_check` the live job uses, judged on the referral's ledger as it
stands now, so a customer who has since played the deposit through properly
keeps the agent's commission) and claws back the excess:

* pending: the amount is corrected (or the commission rejected); no money moved yet.
* approved or paid: the amount is corrected, and the excess comes back:
    1. first from the agent's unpaid affiliate balance,
    2. then from the agent's Winnings wallet (an `adjustment` debit, never below 0),
    3. anything still missing is carried as a negative balance and netted off the
       agent's future commissions automatically.
  Steps 2 and 3 are recorded as one correcting Payout row (wallet / paid,
  possibly negative) so `services.balance()` stays exact.

Commissions staff paid with the rules waived are reported, not touched, unless
`include_waived`. Idempotent: a second run finds nothing to claw back.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.wallet import services as wallet_services

from . import services
from .models import Affiliate, AffiliateProgramme, Commission, Payout

ZERO = Decimal('0.00')
CLAWBACK_NOTE = 'CPA clawback'


@dataclass
class Row:
    commission_id: int
    affiliate_id: int
    affiliate_code: str
    player_id: int
    status: str
    created_at: object
    first_deposit: Optional[Decimal]
    deposits: Decimal
    real_turnover: Decimal
    paid: Decimal
    correct: Decimal
    reason: str
    waived: bool

    @property
    def excess(self) -> Decimal:
        return self.paid - self.correct


@dataclass
class AffiliateResult:
    affiliate_id: int
    code: str
    rows: list[Row] = field(default_factory=list)
    from_balance: Decimal = ZERO
    from_wallet: Decimal = ZERO
    carried: Decimal = ZERO          # still owed; nets off future commissions
    reversed: Decimal = ZERO         # approved/paid excess actually reversed by --apply

    @property
    def excess(self) -> Decimal:
        return sum((r.excess for r in self.rows if r.status != Commission.Status.PENDING), ZERO)


def _review(affiliate: Affiliate, *, include_waived: bool) -> list[Row]:
    """Every live CPA commission of this agent whose amount exceeds what the
    current rules pay (waived ones included in the list, flagged)."""
    commissions = list(affiliate.commissions.filter(kind=Commission.Kind.CPA)
                       .exclude(status=Commission.Status.REJECTED).select_related('referral'))
    if not commissions:
        return []
    ids = [c.referral.player_id for c in commissions]
    totals = services._cpa_totals(ids)
    firsts = wallet_services.first_deposit_amounts(ids)
    multiple = AffiliateProgramme.load().cpa_min_turnover_multiple
    links = services._agent_links(affiliate)
    rows = []
    for c in commissions:
        pid = c.referral.player_id
        t = totals.get(pid, {})
        first = firsts.get(pid)
        correct, reason = services._cpa_check(affiliate, t, first, multiple, linked=pid in links)
        correct = min(correct, c.amount)                 # never pay more than was paid
        waived = 'rules waived' in (c.note or '')
        if c.amount - correct < Decimal('0.01'):
            continue
        rows.append(Row(
            commission_id=c.id, affiliate_id=affiliate.id, affiliate_code=affiliate.code, player_id=pid,
            status=c.status, created_at=c.created_at, first_deposit=first,
            deposits=t.get('deposit', ZERO), real_turnover=t.get('real_turnover', ZERO),
            paid=c.amount, correct=correct, reason=reason or 'terms changed', waived=waived,
        ))
    return rows


def _sum(qs) -> Decimal:
    return services._sum(qs)


def _apply(affiliate: Affiliate, rows: list[Row], result: AffiliateResult, *, by: str) -> None:
    """Correct the commissions and recover the money. Caller holds the
    affiliate row lock (the same lock the automatic payout sweep takes)."""
    stamp = timezone.now()
    spent = _sum(affiliate.payouts.filter(status__in=(Payout.Status.REQUESTED, Payout.Status.PAID)))
    left_before = _sum(affiliate.commissions.filter(status=Commission.Status.APPROVED)) - spent
    legacy_excess = ZERO      # PAID commissions went straight to the wallet (pre-payout era)
    excess = ZERO             # approved + paid excess actually reversed (pending moved no money)
    applied = []
    for r in rows:
        c = Commission.objects.select_for_update().get(pk=r.commission_id)
        if c.amount != r.paid or c.status != r.status:   # changed under us; the next run sees it
            continue
        applied.append(r)
        note = (f'{CLAWBACK_NOTE} {stamp:%Y-%m-%d}: {r.paid} -> {r.correct} ({r.reason})'
                + (f' by {by}' if by else '') + f' | {c.note}')[:500]
        if c.status == Commission.Status.PAID:
            legacy_excess += r.excess
        if c.status != Commission.Status.PENDING:
            excess += r.excess
        c.amount = r.correct
        c.note = note
        fields = ['amount', 'note']
        if r.correct <= 0:
            c.status = Commission.Status.REJECTED
            c.decided_at = stamp
            fields += ['status', 'decided_at']
        c.save(update_fields=fields)

    result.rows = applied
    # The unpaid balance absorbs what it can; the rest has already left it.
    owed = excess - max(left_before, ZERO)
    result.from_balance = excess - max(owed, ZERO)
    recovered = ZERO
    if owed > 0:
        winnings = wallet_services.get_balances(affiliate.player_id)['winnings']
        recovered = min(owed, winnings).quantize(Decimal('0.01'))
        if recovered > 0:
            key = hashlib.sha256(
                ','.join(f'{r.commission_id}:{r.paid}:{r.correct}' for r in applied).encode()).hexdigest()[:40]
            wallet_services.debit(
                player_id=affiliate.player_id, amount=recovered, kind='adjustment', bucket='winnings',
                idempotency_key=f'affiliate-cpa-clawback:{affiliate.id}:{key}',
                reference=f'{CLAWBACK_NOTE}: commissions {",".join(str(r.commission_id) for r in applied)}'[:255],
            )
    result.from_wallet = recovered
    result.carried = max(owed - recovered, ZERO)
    # Keep balance() exact: legacy excess the balance absorbed or that is still
    # owed counts as already paid; money taken back from the wallet un-pays it.
    correction = legacy_excess - recovered
    if correction != 0:
        Payout.objects.create(
            affiliate=affiliate, amount=correction, method=Payout.Method.WALLET, status=Payout.Status.PAID,
            decided_at=stamp,
            note=(f'{CLAWBACK_NOTE}: {excess} reversed — {result.from_balance} from the affiliate '
                  f'balance, {recovered} from the Winnings wallet, {result.carried} netted off future '
                  f'commissions' + (f' (by {by})' if by else ''))[:500],
        )


def run(*, affiliate_ids: Optional[list[int]] = None, apply: bool = False, include_waived: bool = False,
        by: str = '') -> list[AffiliateResult]:
    """Review (and with `apply`, reverse) every over-paid CPA commission since
    the programme started. Each agent is handled in its own transaction."""
    qs = Affiliate.objects.filter(commissions__kind=Commission.Kind.CPA).distinct().order_by('pk')
    if affiliate_ids:
        qs = qs.filter(pk__in=affiliate_ids)
    results = []
    for aid in qs.values_list('pk', flat=True):
        with transaction.atomic():
            affiliate = Affiliate.objects.select_for_update().get(pk=aid)
            rows = _review(affiliate, include_waived=include_waived)
            if not rows:
                continue
            result = AffiliateResult(affiliate_id=affiliate.id, code=affiliate.code, rows=rows)
            to_fix = [r for r in rows if include_waived or not r.waived]
            if apply and to_fix:
                fix = AffiliateResult(affiliate_id=affiliate.id, code=affiliate.code, rows=to_fix)
                _apply(affiliate, to_fix, fix, by=by)
                result.from_balance, result.from_wallet, result.carried = fix.from_balance, fix.from_wallet, fix.carried
                result.reversed = fix.excess
            results.append(result)
    return results
