"""wallet fault-tolerance — ledger reconciliation.

Recovery strategy
-----------------
The cached `Wallet.balance` can drift from the append-only ledger if a process
dies between writing a `LedgerEntry` and updating the balance (the two happen in
one transaction, so this is rare — but recovery makes it self-healing). This
manager recomputes each wallet's authoritative balance as the SUM of its ledger
entries and corrects the cached value.

Idempotency
-----------
The ledger is immutable, so `SUM(entries)` is a pure function of state. Setting
`balance = SUM(entries)` is naturally idempotent: running it once or a thousand
times yields the same number, and it NEVER creates ledger rows. A second run
simply finds no drift and repairs nothing.
"""
from __future__ import annotations

from django.db import transaction

from common.recovery import BaseRecoveryManager, RecoveryReport

from . import services, utils
from .models import Wallet


class RecoveryManager(BaseRecoveryManager):
    domain = 'wallet'

    def reconcile(self) -> None:
        for wallet in Wallet.objects.all().iterator():
            self.mark_scanned()
            authoritative = services.recompute_balance(wallet.player_id)
            cached = utils.quantize(wallet.balance)
            if cached == authoritative:
                continue
            detail = f'wallet player={wallet.player_id} drift {cached} -> {authoritative}'
            if self.dry_run:
                self.mark_skipped(detail)
                continue
            with transaction.atomic():
                locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
                locked.balance = authoritative
                locked.save(update_fields=['balance', 'updated_at'])
            self.mark_repaired(detail)


def reconcile_wallet_ledger(*, dry_run: bool = False) -> RecoveryReport:
    """Module-level entry point (matches the domain's named recovery routine)."""
    return RecoveryManager(dry_run=dry_run).run()
