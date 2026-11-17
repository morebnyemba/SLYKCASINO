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
import re
from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.wallet import services as wallet_services

from . import services
from .models import Affiliate, AffiliateProgramme, Commission, CommissionReversal, Payout

ZERO = Decimal('0.00')
CLAWBACK_NOTE = 'CPA clawback'
# How long agents' dashboards explain the audit: everyone, then those affected.
NOTICE_ALL_DAYS = 30
NOTICE_AFFECTED_DAYS = 90
_RESTORED = re.compile(r'^CPA restored \d{4}-\d{2}-\d{2}: ([\d.]+) -> ([\d.]+)(?: of ([\d.]+))?(?: \((.*?)\))?')
_NOTE = re.compile(r'^CPA clawback (\d{4}-\d{2}-\d{2}): ([\d.]+) -> ([\d.]+) \((.*?)\)(?: by [^|]*)? \|')


@dataclass
class Row:
    commission_id: int
    affiliate_id: int
    affiliate_code: str
    player_id: Optional[int]
    status: str
    created_at: object
    first_deposit: Optional[Decimal]
    deposits: Decimal
    real_turnover: Decimal
    paid: Decimal
    correct: Decimal
    reason: str
    waived: bool
    deleted: bool = False

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
    current rules pay (waived ones included in the list, flagged). A commission
    whose customer has since been deleted can't be re-checked (their ledger is
    gone): it is listed with `deleted` set and the whole amount as excess."""
    commissions = list(affiliate.commissions.filter(kind=Commission.Kind.CPA)
                       .exclude(status=Commission.Status.REJECTED).select_related('referral'))
    if not commissions:
        return []
    ids = [c.referral.player_id for c in commissions if c.referral is not None]
    totals = services._cpa_totals(ids)
    firsts = wallet_services.first_deposit_amounts(ids) if ids else {}
    multiple = AffiliateProgramme.load().cpa_min_turnover_multiple
    links = services._agent_links(affiliate)
    rows = []
    for c in commissions:
        waived = 'rules waived' in (c.note or '')
        if c.referral is None:
            if c.amount >= Decimal('0.01'):
                rows.append(Row(
                    commission_id=c.id, affiliate_id=affiliate.id, affiliate_code=affiliate.code, player_id=None,
                    status=c.status, created_at=c.created_at, first_deposit=c.base_amount, deposits=ZERO,
                    real_turnover=ZERO, paid=c.amount, correct=ZERO,
                    reason='the customer’s account has been deleted, so it can’t be checked', waived=waived,
                    deleted=True,
                ))
            continue
        pid = c.referral.player_id
        t = totals.get(pid, {})
        first = firsts.get(pid)
        correct, reason = services._cpa_check(affiliate, t, first, multiple, linked=pid in links)
        correct = min(correct, c.amount)                 # never pay more than was paid
        if c.amount - correct < Decimal('0.01'):
            continue
        rows.append(Row(
            commission_id=c.id, affiliate_id=affiliate.id, affiliate_code=affiliate.code, player_id=pid,
            status=c.status, created_at=c.created_at, first_deposit=first,
            deposits=t.get('deposit', ZERO), real_turnover=t.get('real_turnover', ZERO),
            paid=c.amount, correct=correct, reason=reason or 'terms changed', waived=waived,
        ))
    return rows


def charged_to_pool(decided_at, *, at) -> bool:
    """Whether a commission that became final at `decided_at` was charged to
    the operating pool by `at`: its day has been closed (revenue days close in
    order, each charging that day's final commissions)."""
    if decided_at is None:
        return False
    from apps.revenue.models import RevenueDay
    return RevenueDay.objects.filter(day=timezone.localdate(decided_at), closed_at__lt=at).exists()


def record_reversal(c: Commission, amount: Decimal, *, reason: str, at) -> CommissionReversal:
    """Note money taken back from a final commission, so the pool gets it back."""
    return CommissionReversal.objects.create(
        commission=c, affiliate_id=c.affiliate_id, amount=amount, reason=reason[:300], created_at=at,
        counted=charged_to_pool(c.decided_at or c.created_at, at=at),
    )


def _sum(qs) -> Decimal:
    return services._sum(qs)


def _apply(affiliate: Affiliate, rows: list[Row], result: AffiliateResult, *, by: str, label: str = CLAWBACK_NOTE,
           notify: Optional[tuple[str, str]] = None) -> None:
    """Correct the commissions and recover the money. Caller holds the
    affiliate row lock (the same lock the automatic payout sweep takes).
    `label` starts every note and wallet reference (the audit's by default);
    `notify` is the agent's (title, body), `{excess}` filled in."""
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
        note = (f'{label} {stamp:%Y-%m-%d}: {r.paid} -> {r.correct} ({r.reason})'
                + (f' by {by}' if by else '') + f' | {c.note}')[:500]
        if c.status == Commission.Status.PAID:
            legacy_excess += r.excess
        if c.status != Commission.Status.PENDING:
            excess += r.excess
            # Before decided_at is overwritten: was this amount charged to the pool?
            record_reversal(c, r.excess, reason=r.reason, at=stamp)
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
                reference=f'{label}: commissions {",".join(str(r.commission_id) for r in applied)}'[:255],
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
            note=(f'{label}: {excess} reversed — {result.from_balance} from the affiliate '
                  f'balance, {recovered} from the Winnings wallet, {result.carried} netted off future '
                  f'commissions' + (f' (by {by})' if by else ''))[:500],
        )
    if excess > 0:
        title, body = notify or ('Commission audit: some deposit commissions reversed',
                                 '{excess} in deposit commissions for customers who did not meet the programme rules has '
                                 'been reversed. Open your agent dashboard for the details.')
        services._notify(affiliate, title, body.format(excess=excess))


def skipped(r: Row, *, include_waived: bool, include_deleted: bool) -> str:
    """Why a reviewed row is left alone ('' = it gets reversed)."""
    if r.waived and not include_waived:
        return 'staff waived the rules'
    if r.deleted and not include_deleted:
        return 'customer deleted'
    return ''


def run(*, affiliate_ids: Optional[list[int]] = None, apply: bool = False, include_waived: bool = False,
        include_deleted: bool = False, by: str = '') -> list[AffiliateResult]:
    """Review (and with `apply`, reverse) every over-paid CPA commission since
    the programme started. Each agent is handled in its own transaction."""
    qs = Affiliate.objects.filter(commissions__kind=Commission.Kind.CPA).distinct().order_by('pk')
    if affiliate_ids:
        qs = qs.filter(pk__in=affiliate_ids)
    results = []
    if apply and not affiliate_ids:      # a full audit: every agent's dashboard explains it
        AffiliateProgramme.load()
        AffiliateProgramme.objects.filter(pk=1).update(cpa_audit_at=timezone.now())
    for aid in qs.values_list('pk', flat=True):
        with transaction.atomic():
            affiliate = Affiliate.objects.select_for_update().get(pk=aid)
            rows = _review(affiliate, include_waived=include_waived)
            if not rows:
                continue
            result = AffiliateResult(affiliate_id=affiliate.id, code=affiliate.code, rows=rows)
            to_fix = [r for r in rows
                      if not skipped(r, include_waived=include_waived, include_deleted=include_deleted)]
            if apply and to_fix:
                fix = AffiliateResult(affiliate_id=affiliate.id, code=affiliate.code, rows=to_fix)
                _apply(affiliate, to_fix, fix, by=by)
                result.from_balance, result.from_wallet, result.carried = fix.from_balance, fix.from_wallet, fix.carried
                result.reversed = fix.excess
            results.append(result)
    return results


def _reason_for_agent(reason: str) -> str:
    """The rule a customer missed, as the agent reads it."""
    if reason.startswith('bet '):
        return 'the customer ' + reason.replace(' needed', ' needed in their own money (bonus money doesn’t count)')
    if reason.startswith('deposited '):
        return 'the customer ' + reason
    if 'payment number' in reason:
        return 'the customer’s account shares a payment number with yours'
    return reason


OLD_DEPOSIT_PERCENT = Decimal('30')     # the old terms: 30% of a customer's first deposit…
OLD_LOST_PERCENT = Decimal('30')        # …plus 30% of every losing stake


# An illustration for agents, deliberately NOT the house's real figures:
# winners are paid back 90c of every 1.00 staked, and the payment provider
# takes a few cents of a deposit.
EXAMPLE_HOUSE_KEEPS_CENTS = Decimal('10')
EXAMPLE_PAYMENT_FEE_CENTS = Decimal('3')


def _c(v: Decimal) -> str:
    return f'{v.normalize():f}'


def economics() -> dict:
    """The worked example behind the audit, for agents: what the old terms paid
    on a customer who deposits 1.00 and loses it, against an illustrative house
    margin and payment charge. Fixed numbers, labelled as an example: nothing
    here is read from the ledger or reveals the house's real margin or costs."""
    agent = OLD_DEPOSIT_PERCENT + OLD_LOST_PERCENT                     # cents per 1.00
    kept, fee = EXAMPLE_HOUSE_KEEPS_CENTS, EXAMPLE_PAYMENT_FEE_CENTS
    return {
        'deposit_percent': _c(OLD_DEPOSIT_PERCENT), 'lost_percent': _c(OLD_LOST_PERCENT), 'agent_cents': _c(agent),
        'example_kept_cents': _c(kept), 'example_winnings_cents': _c(Decimal('100') - kept),
        'example_fee_cents': _c(fee), 'example_result_cents': _c(kept - agent - fee),
    }


def notice(affiliate: Affiliate, *, now=None) -> Optional[dict]:
    """What the agent's dashboard says about the CPA audit: to everyone for
    NOTICE_ALL_DAYS after it ran, and — with exactly what was reversed and how
    it was recovered — to affected agents for NOTICE_AFFECTED_DAYS. None when
    there is nothing to say."""
    programme = AffiliateProgramme.load()
    audited = programme.cpa_audit_at
    if audited is None:
        return None
    now = now or timezone.now()
    from django.db.models import Q
    reversed_qs = list(affiliate.commissions.filter(kind=Commission.Kind.CPA)
                       .filter(Q(note__startswith=CLAWBACK_NOTE) | Q(note__startswith='CPA restored'))
                       .select_related('referral').order_by('created_at'))
    affected = bool(reversed_qs)
    if now > audited + timedelta(days=NOTICE_AFFECTED_DAYS if affected else NOTICE_ALL_DAYS):
        return None
    names = services.accounts_services.usernames_for([c.referral.player_id for c in reversed_qs if c.referral])
    items, total = [], ZERO
    for c in reversed_qs:
        m = _NOTE.match(c.note or '')
        if m:
            paid, kept, reason = Decimal(m.group(2)), Decimal(m.group(3)), _reason_for_agent(m.group(4))
        else:
            r = _RESTORED.match(c.note or '')
            if not r or not r.group(3) or Decimal(r.group(3)) - Decimal(r.group(2)) < Decimal('0.01'):
                continue                                   # fully restored: nothing left to explain
            paid, kept = Decimal(r.group(3)), Decimal(r.group(2))
            why = r.group(4) or ''
            reason = (why[0].upper() + why[1:] + '. The rest stays reversed.') if why else 'Partly restored; the rest stays reversed.'
        total += paid - kept
        pid = c.referral.player_id if c.referral else None
        items.append({
            'customer': services._shown(names.get(pid, '?'), True), 'earned_on': c.created_at.date(),
            'paid': f'{paid:.2f}', 'kept': f'{kept:.2f}', 'reversed': f'{paid - kept:.2f}',
            'reason': reason,
        })
    from apps.wallet.models import LedgerEntry
    from django.db.models import Sum
    from_wallet = max(-(LedgerEntry.objects.filter(wallet__player_id=affiliate.player_id, kind='adjustment',
                                                   reference__regex=r'^(CPA clawback|CPA restored)')
                        .aggregate(v=Sum('amount'))['v'] or ZERO), ZERO)
    restored = [m for m in (_RESTORED.match(n or '') for n in affiliate.commissions.filter(
        kind=Commission.Kind.CPA, note__startswith='CPA restored').values_list('note', flat=True)) if m]
    restored_total = sum((Decimal(m.group(2)) - Decimal(m.group(1)) for m in restored), ZERO)
    rate = next((p.group(1) for p in (re.search(r'restored at ([\d.]+)%', m.group(4) or '') for m in restored) if p), '')
    approved = services._sum(affiliate.commissions.filter(status=Commission.Status.APPROVED))
    spent = services._sum(affiliate.payouts.filter(status__in=(Payout.Status.REQUESTED, Payout.Status.PAID)))
    return {
        'audited_on': timezone.localdate(audited),
        'affected': affected,
        'turnover_multiple': str(programme.cpa_min_turnover_multiple),
        'min_deposit': str(affiliate.cpa_min_deposit),
        'reversed_total': f'{total:.2f}',
        'from_wallet': f'{from_wallet:.2f}',
        'from_balance': f'{max(total - from_wallet - max(spent - approved, ZERO), ZERO):.2f}',
        'still_owed': f'{max(spent - approved, ZERO):.2f}',
        'restored_total': f'{restored_total:.2f}',
        'restored_count': len(restored),
        'restored_percent': rate,
        'economics': economics(),
        'items': items,
    }
