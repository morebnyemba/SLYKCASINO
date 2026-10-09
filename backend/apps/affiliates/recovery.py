"""affiliates fault-tolerance — payouts into the betting wallet.

Recovery strategy
-----------------
A payout to the betting wallet is credited as soon as it's requested. If that
is interrupted (the request row exists but is still REQUESTED), past a grace
window the credit is re-driven with the payout's deterministic key
`wallet:affiliate-payout:<id>:credit`, then the payout is marked PAID.
Mobile-money and bank payouts wait for an operator and are never touched.

Idempotency
-----------
The credit is keyed per payout, so it can never land twice; only
REQUESTED -> PAID transitions happen, so repeat runs are no-ops.
"""
from __future__ import annotations

from datetime import timedelta

from django.utils import timezone

from common.recovery import BaseRecoveryManager

from . import services
from .models import Payout

GRACE = timedelta(minutes=5)


class RecoveryManager(BaseRecoveryManager):
    domain = 'affiliates'

    def reconcile(self) -> None:
        cutoff = timezone.now() - GRACE
        stuck = Payout.objects.filter(
            status=Payout.Status.REQUESTED, method=Payout.Method.WALLET, created_at__lt=cutoff,
        )
        for payout in stuck.iterator():
            self.mark_scanned()
            if self.dry_run:
                self.mark_skipped(f'would complete wallet payout {payout.id}')
                continue
            try:
                services.complete_wallet_payout(payout.id)
                self.mark_repaired(f'payout {payout.id}: wallet credit re-driven')
            except Exception as exc:  # noqa: BLE001
                self.mark_failed(f'payout {payout.id}: {exc!r}')
