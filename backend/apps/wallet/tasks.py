"""wallet Celery tasks — scheduled reconciliation entry points."""
from __future__ import annotations

from celery import shared_task

from .recovery import RecoveryManager


@shared_task(name='apps.wallet.tasks.reconcile_ledger')
def reconcile_ledger(dry_run: bool = False) -> dict:
    return RecoveryManager(dry_run=dry_run).run().model_dump(mode='json')
