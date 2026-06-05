"""sportsbook fault-tolerance — orphaned bet states.

Recovery strategy
-----------------
A bet can be orphaned in `PENDING` if a placement is interrupted between writing
the Bet row and confirming the stake debit. This manager finds PENDING bets past
a grace window and reconciles each against the wallet ledger:

  * stake debit already present  -> promote bet to OPEN
  * debit absent, funds available -> drive the (idempotency-keyed) debit, then OPEN
  * debit absent, no funds        -> VOID the bet (nothing was charged)

Idempotency
-----------
The stake debit uses the deterministic key `wallet:bet:<id>:stake`. Re-running
finds the entry already posted and just promotes to OPEN — it can never debit
twice. Bets already OPEN/settled are ignored.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.wallet import services as wallet_services
from apps.wallet.models import LedgerEntry

from common.recovery import BaseRecoveryManager, RecoveryReport

from . import helpers
from .models import Bet

GRACE = timedelta(minutes=2)


class RecoveryManager(BaseRecoveryManager):
    domain = 'sportsbook'

    def reconcile(self) -> None:
        cutoff = timezone.now() - GRACE
        orphaned = Bet.objects.filter(status=Bet.Status.PENDING, placed_at__lt=cutoff)
        for bet in orphaned.iterator():
            self.mark_scanned()
            if self.dry_run:
                self.mark_skipped(f'would reconcile orphaned bet {bet.id}')
                continue
            self._reconcile_one(bet)

    def _reconcile_one(self, bet: Bet) -> None:
        key = helpers.stake_idempotency_key(bet.id)
        debited = LedgerEntry.objects.filter(idempotency_key=key).exists()
        try:
            with transaction.atomic():
                locked = Bet.objects.select_for_update().get(pk=bet.id)
                if locked.status != Bet.Status.PENDING:
                    return  # someone else handled it
                if debited:
                    locked.status = Bet.Status.OPEN
                    locked.save(update_fields=['status'])
                    self.mark_repaired(f'bet {bet.id}: debit found, promoted to OPEN')
                    return
                if locked.player_id and wallet_services.get_balance(locked.player_id) >= locked.stake:
                    wallet_services.debit(
                        player_id=locked.player_id, amount=locked.stake, kind='bet_stake',
                        idempotency_key=key, reference=f'bet:{locked.id}',
                    )
                    locked.status = Bet.Status.OPEN
                    locked.save(update_fields=['status'])
                    self.mark_repaired(f'bet {bet.id}: drove stake debit, promoted to OPEN')
                else:
                    locked.status = Bet.Status.VOID
                    locked.settled_at = timezone.now()
                    locked.save(update_fields=['status', 'settled_at'])
                    self.mark_repaired(f'bet {bet.id}: no funds/charge, voided')
        except Exception as exc:  # noqa: BLE001
            self.mark_failed(f'bet {bet.id}: {exc!r}')


def handle_orphaned_bet_states(*, dry_run: bool = False) -> RecoveryReport:
    """Module-level entry point (matches the domain's named recovery routine)."""
    return RecoveryManager(dry_run=dry_run).run()
