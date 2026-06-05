"""promotions fault-tolerance — claim reconciliation.

Recovery strategy
-----------------
Two inconsistencies are reconciled:

  1. *Uncredited bonuses* — a claim exists but its bonus credit didn't land
     (crash between claim creation and wallet credit). Re-credit using the
     deterministic key `wallet:promo:<claim>:bonus`.
  2. *Expired claims* — an ACTIVE claim whose promotion window closed is moved
     to EXPIRED.

Idempotency
-----------
Bonus re-credit is keyed per claim, so a duplicate credit is impossible. The
`bonus_credited` flag is flipped only after the keyed credit. Expiry only
transitions ACTIVE -> EXPIRED, so repeat runs are no-ops.
"""
from __future__ import annotations

from django.db import transaction
from django.utils import timezone

from apps.wallet import services as wallet_services

from common.recovery import BaseRecoveryManager, RecoveryReport

from . import helpers
from .models import PromotionClaim


class RecoveryManager(BaseRecoveryManager):
    domain = 'promotions'

    def reconcile(self) -> None:
        self._recredit_uncredited()
        self._expire_stale()

    def _recredit_uncredited(self) -> None:
        pending = PromotionClaim.objects.filter(bonus_credited=False, bonus_amount__gt=0)
        for claim in pending.iterator():
            self.mark_scanned()
            if self.dry_run:
                self.mark_skipped(f'would credit bonus for claim {claim.id}')
                continue
            try:
                with transaction.atomic():
                    locked = PromotionClaim.objects.select_for_update().get(pk=claim.id)
                    if locked.bonus_credited:
                        continue
                    wallet_services.credit(
                        player_id=locked.player_id, amount=locked.bonus_amount, kind='bonus',
                        idempotency_key=helpers.bonus_credit_key(locked.id),
                        reference=f'claim:{locked.id}',
                    )
                    locked.bonus_credited = True
                    locked.save(update_fields=['bonus_credited'])
                self.mark_repaired(f'claim {claim.id}: bonus credited')
            except Exception as exc:  # noqa: BLE001
                self.mark_failed(f'claim {claim.id}: {exc!r}')

    def _expire_stale(self) -> None:
        now = timezone.now()
        stale = PromotionClaim.objects.filter(
            status=PromotionClaim.Status.ACTIVE,
            promotion__ends_at__lt=now,
        )
        for claim in stale.iterator():
            self.mark_scanned()
            if self.dry_run:
                self.mark_skipped(f'would expire claim {claim.id}')
                continue
            updated = PromotionClaim.objects.filter(
                pk=claim.id, status=PromotionClaim.Status.ACTIVE,
            ).update(status=PromotionClaim.Status.EXPIRED)
            if updated:
                self.mark_repaired(f'claim {claim.id}: expired')


def reconcile_promotion_claims(*, dry_run: bool = False) -> RecoveryReport:
    """Module-level entry point (matches the domain's named recovery routine)."""
    return RecoveryManager(dry_run=dry_run).run()
