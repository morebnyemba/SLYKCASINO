"""casino fault-tolerance — retry the stake-debit sequence for stuck rounds.

Recovery strategy
-----------------
A round can be left PENDING with `debit_confirmed=False` if the worker dies
between creating the round and confirming the wallet debit. This manager finds
such rounds past a grace window and reconciles each against the ledger:

  * debit entry present  -> mark `debit_confirmed=True` (and keep/settle round)
  * debit absent, funds   -> drive the (idempotency-keyed) debit, confirm
  * debit absent, no funds -> VOID the round (nothing was charged)

Idempotency
-----------
The debit uses the deterministic key `wallet:casino:<id>:debit`. Re-running can
never debit twice — it finds the entry and only flips the confirmation flag.
"""
from __future__ import annotations

from datetime import timedelta

from django.db import transaction
from django.utils import timezone

from apps.wallet import services as wallet_services
from apps.wallet.models import LedgerEntry

from common.recovery import BaseRecoveryManager, RecoveryReport

from . import helpers
from .models import GameRound

GRACE = timedelta(minutes=2)


class RecoveryManager(BaseRecoveryManager):
    domain = 'casino'

    def reconcile(self) -> None:
        cutoff = timezone.now() - GRACE
        stuck = GameRound.objects.filter(
            status=GameRound.Status.PENDING, debit_confirmed=False, created_at__lt=cutoff,
        )
        for rnd in stuck.iterator():
            self.mark_scanned()
            if self.dry_run:
                self.mark_skipped(f'would retry debit for round {rnd.id}')
                continue
            self._reconcile_one(rnd.id)

    def _reconcile_one(self, round_id: int) -> None:
        key = helpers.round_debit_key(round_id)
        debited = LedgerEntry.objects.filter(idempotency_key=key).exists()
        try:
            with transaction.atomic():
                rnd = GameRound.objects.select_for_update().get(pk=round_id)
                if rnd.debit_confirmed or rnd.status != GameRound.Status.PENDING:
                    return
                if debited:
                    rnd.debit_confirmed = True
                    rnd.save(update_fields=['debit_confirmed'])
                    self.mark_repaired(f'round {round_id}: debit found, confirmed')
                elif wallet_services.get_balance(rnd.player_id) >= rnd.stake:
                    wallet_services.debit(
                        player_id=rnd.player_id, amount=rnd.stake, kind='casino_debit',
                        idempotency_key=key, reference=f'round:{rnd.id}',
                    )
                    rnd.debit_confirmed = True
                    rnd.save(update_fields=['debit_confirmed'])
                    self.mark_repaired(f'round {round_id}: drove debit, confirmed')
                else:
                    rnd.status = GameRound.Status.VOID
                    rnd.settled_at = timezone.now()
                    rnd.save(update_fields=['status', 'settled_at'])
                    self.mark_repaired(f'round {round_id}: no funds, voided')
        except Exception as exc:  # noqa: BLE001
            self.mark_failed(f'round {round_id}: {exc!r}')


def retry_casino_debit_sequence(*, dry_run: bool = False) -> RecoveryReport:
    """Module-level entry point (matches the domain's named recovery routine)."""
    return RecoveryManager(dry_run=dry_run).run()
