"""Give back deposit commissions (CPA) the audit reversed although they met the
rules in force when they were paid.

The audit (`clawback`) judged every CPA by today's rule: 3x the first deposit
staked in real money. Before that rule, a CPA needed 1x. A commission is
restored when:

* the customer still exists and doesn't share a payment number with the agent,
* the customer deposited at least the agent's minimum and staked at least 1x
  their first deposit in real money (Deposit and Winnings wallets; bonus money
  doesn't count).

On flat-CPA terms (e.g. 5.00 + 20%) only the percentage part is restored: the
flat amount (5.20 on a 1.00 deposit) can't pay for itself and stays reversed.

Restoring undoes what the audit did, for the amount restored:

* the commission goes back to its full amount, approved, earned on its original day;
* the agent's balance rises by that amount (what the audit took from the
  balance comes straight back);
* what the audit took from the agent's Winnings wallet is paid back into it,
  with a matching Payout row so `services.balance()` stays exact;
* the operating pool is charged again (a negative CommissionReversal), unless
  the day it's earned on hasn't closed yet, in which case closing that day
  charges it as usual.

Dry run unless `apply`. Idempotent: a restored commission no longer carries the
clawback note, so a second run finds nothing.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.wallet import services as wallet_services

from . import services, utils
from .clawback import CLAWBACK_NOTE, charged_to_pool
from .models import Affiliate, Commission, CommissionReversal, Payout

ZERO = Decimal('0.00')
RESTORE_NOTE = 'CPA restored'
OLD_MULTIPLE = Decimal('1')       # play-through in force before the audit
_NOTE = re.compile(r'^CPA clawback (\d{4}-\d{2}-\d{2}): ([\d.]+) -> ([\d.]+) \((.*?)\)(?: by [^|]*)? \| ?(.*)$', re.S)


@dataclass
class Row:
    commission_id: int
    player_id: Optional[int]
    first_deposit: Optional[Decimal]
    real_turnover: Decimal
    paid: Decimal          # before the audit
    kept: Decimal          # after the audit
    restore: bool
    why: str               # why it is (not) restored
    target: Decimal = ZERO  # the commission's amount once restored (paid, or the % part on flat terms)

    @property
    def amount(self) -> Decimal:
        """Restored if `restore`, else what stays reversed."""
        return (self.target if self.restore else self.paid) - self.kept


@dataclass
class AgentResult:
    affiliate_id: int
    code: str
    rows: list[Row] = field(default_factory=list)
    restored: Decimal = ZERO
    to_wallet: Decimal = ZERO

    @property
    def due(self) -> Decimal:
        return sum((r.amount for r in self.rows if r.restore), ZERO)


def _review(affiliate: Affiliate) -> list[Row]:
    clawed = list(affiliate.commissions.filter(kind=Commission.Kind.CPA, note__startswith=CLAWBACK_NOTE)
                  .select_related('referral').order_by('created_at'))
    if not clawed:
        return []
    ids = [c.referral.player_id for c in clawed if c.referral is not None]
    totals = services._cpa_totals(ids)
    firsts = wallet_services.first_deposit_amounts(ids) if ids else {}
    links = services._agent_links(affiliate)
    rows = []
    for c in clawed:
        m = _NOTE.match(c.note or '')
        if not m:
            continue
        paid, kept = Decimal(m.group(2)), Decimal(m.group(3))
        if paid - kept < Decimal('0.01'):
            continue
        pid = c.referral.player_id if c.referral else None
        t = totals.get(pid, {}) if pid else {}
        first = firsts.get(pid) if pid else None
        turnover = t.get('real_turnover', ZERO)
        deposits = t.get('deposit', ZERO)
        target = paid
        if pid is None:
            restore, why = False, 'customer deleted'
        elif pid in links:
            restore, why = False, 'shares a payment number with the agent'
        elif first is None or deposits < affiliate.cpa_min_deposit:
            restore, why = False, 'under the minimum deposit'
        elif turnover < first * OLD_MULTIPLE:
            restore, why = False, f'bet {turnover:.2f} real of {first * OLD_MULTIPLE:.2f} (only bonus money qualified it)'
        else:
            restore, why = True, f'bet {turnover:.2f} real of the {first * OLD_MULTIPLE:.2f} needed when paid'
            if affiliate.cpa_amount > 0:
                target = min(paid, utils.deposit_commission(first, ZERO, affiliate.cpa_percent, affiliate.cpa_cap))
                why += '; percentage part only, the flat CPA stays reversed'
                if target - kept < Decimal('0.01'):
                    restore, why = False, 'flat CPA terms, no percentage part to give back'
        rows.append(Row(commission_id=c.id, player_id=pid, first_deposit=first, real_turnover=turnover,
                        paid=paid, kept=kept, restore=restore, why=why, target=target))
    return rows


def _wallet_taken(affiliate: Affiliate) -> Decimal:
    """What the audit took from the agent's Winnings wallet, less what a
    restore has already paid back."""
    from apps.wallet.models import LedgerEntry
    total = (LedgerEntry.objects
             .filter(wallet__player_id=affiliate.player_id, kind='adjustment')
             .filter(reference__regex=r'^(CPA clawback|CPA restored)')
             .aggregate(v=Sum('amount'))['v'] or ZERO)
    return max(-total, ZERO)


def _apply(affiliate: Affiliate, rows: list[Row], result: AgentResult, *, by: str) -> None:
    stamp = timezone.now()
    restored = ZERO
    done = []
    for r in rows:
        c = Commission.objects.select_for_update().get(pk=r.commission_id)
        m = _NOTE.match(c.note or '')
        if not m or Decimal(m.group(3)) != c.amount:      # changed since the review
            continue
        original_note = m.group(5)
        c.amount = r.target
        c.status = Commission.Status.APPROVED
        c.decided_at = c.created_at                       # earned on its original day
        c.note = (f'{RESTORE_NOTE} {stamp:%Y-%m-%d}: {r.kept} -> {r.target} of {r.paid} ({r.why})'
                  + (f' by {by}' if by else '') + (f' | {original_note}' if original_note else ''))[:500]
        c.save(update_fields=['amount', 'status', 'decided_at', 'note'])
        # The pool charges a final commission when its day closes. That day has
        # already closed: charge it again through a negative reversal.
        if charged_to_pool(c.decided_at, at=stamp):
            CommissionReversal.objects.create(commission=c, affiliate=affiliate, amount=-r.amount,
                                              reason='restored after the audit', counted=True, created_at=stamp)
        restored += r.amount
        done.append(r)
    result.restored = restored
    if restored <= 0:
        return
    # Money the audit took out of the Winnings wallet goes back into it.
    refund = min(restored, _wallet_taken(affiliate)).quantize(Decimal('0.01'))
    if refund > 0:
        key = ','.join(str(r.commission_id) for r in done)
        digest = hashlib.sha256(f'{key}:{refund}'.encode()).hexdigest()[:40]
        wallet_services.credit(
            player_id=affiliate.player_id, amount=refund, kind='adjustment', bucket='winnings',
            idempotency_key=f'affiliate-cpa-restore:{affiliate.id}:{digest}',
            reference=f'{RESTORE_NOTE}: commissions {key}'[:255],
        )
        Payout.objects.create(affiliate=affiliate, amount=refund, method=Payout.Method.WALLET,
                              status=Payout.Status.PAID, decided_at=stamp,
                              note=f'{RESTORE_NOTE}: {refund} paid back to the Winnings wallet'[:500])
    result.to_wallet = refund
    services._notify(affiliate, 'Commission audit: commissions restored',
                     f'{restored} in deposit commissions has been restored: those customers met the rules in force '
                     'when the commission was paid. Open your agent dashboard for the details.')


def run(*, affiliate_ids: Optional[list[int]] = None, apply: bool = False, by: str = '') -> list[AgentResult]:
    qs = Affiliate.objects.filter(commissions__note__startswith=CLAWBACK_NOTE).distinct().order_by('pk')
    if affiliate_ids:
        qs = qs.filter(pk__in=affiliate_ids)
    results = []
    for aid in qs.values_list('pk', flat=True):
        with transaction.atomic():
            affiliate = Affiliate.objects.select_for_update().get(pk=aid)
            rows = _review(affiliate)
            if not rows:
                continue
            result = AgentResult(affiliate_id=affiliate.id, code=affiliate.code, rows=rows)
            to_restore = [r for r in rows if r.restore]
            if apply and to_restore:
                _apply(affiliate, to_restore, result, by=by)
            results.append(result)
    return results
