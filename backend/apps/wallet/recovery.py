"""wallet fault-tolerance — ledger reconciliation.

Recovery strategy
-----------------
The cached bucket balances (deposit / bonus / winnings) and their total can drift from the append-only ledger if a process
dies between writing a `LedgerEntry` and updating the balance (the two happen in
one transaction, so this is rare — but recovery makes it self-healing). This
manager recomputes each bucket's authoritative balance as the SUM of its ledger
entries and corrects the cached values. Every correction is also written to the
staff audit log (`ledger_drift`) — drift means something went wrong and is a
discrepancy to investigate, not just to fix.

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
from .models import BALANCE_FIELD, Bucket, Wallet


class RecoveryManager(BaseRecoveryManager):
    domain = 'wallet'

    def reconcile(self) -> None:
        for wallet in Wallet.objects.all().iterator():
            self.mark_scanned()
            authoritative = services.recompute_balances(wallet.player_id)
            cached = {b: utils.quantize(wallet.bucket_balance(b)) for b in Bucket.values}
            total = utils.quantize(sum(authoritative.values()))
            if cached == authoritative and utils.quantize(wallet.balance) == total:
                continue
            drift = {b: f'{cached[b]} -> {authoritative[b]}' for b in Bucket.values if cached[b] != authoritative[b]}
            detail = f'wallet player={wallet.player_id} drift {drift or {"total": f"{wallet.balance} -> {total}"}}'
            if self.dry_run:
                self.mark_skipped(detail)
                continue
            with transaction.atomic():
                locked = Wallet.objects.select_for_update().get(pk=wallet.pk)
                for bucket, amount in authoritative.items():
                    setattr(locked, BALANCE_FIELD[bucket], amount)
                locked.balance = total
                locked.save(update_fields=[*BALANCE_FIELD.values(), 'balance', 'updated_at'])
                from apps.accounts import services as accounts_services
                accounts_services.audit(wallet.player_id, 'ledger_drift', None, drift=drift, total=str(total))
            self.mark_repaired(detail)


def reconcile_wallet_ledger(*, dry_run: bool = False) -> RecoveryReport:
    """Module-level entry point (matches the domain's named recovery routine)."""
    return RecoveryManager(dry_run=dry_run).run()
