"""affiliates fault-tolerance — commission payouts.

Recovery strategy
-----------------
A commission can be left APPROVED if payment is interrupted between approval
and the wallet credit. Past a grace window, the credit is re-driven with the
commission's deterministic key `wallet:affiliate:<id>:payout`, then the
commission is marked PAID.

Idempotency
-----------
The credit is keyed per commission, so it can never land twice; only
APPROVED -> PAID transitions happen, so repeat runs are no-ops.
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from common.recovery import BaseRecoveryManager

from . import services
from .models import Commission

GRACE = timedelta(minutes=5)


class RecoveryManager(BaseRecoveryManager):
    domain = 'affiliates'

    def reconcile(self) -> None:
        cutoff = timezone.now() - GRACE
        stuck = Commission.objects.filter(status=Commission.Status.APPROVED, decided_at__lt=cutoff)
        for commission in stuck.iterator():
            self.mark_scanned()
            if self.dry_run:
                self.mark_skipped(f'would pay commission {commission.id}')
                continue
            try:
                services.approve(commission.id)
                self.mark_repaired(f'commission {commission.id}: payout re-driven')
            except Exception as exc:  # noqa: BLE001
                self.mark_failed(f'commission {commission.id}: {exc!r}')
