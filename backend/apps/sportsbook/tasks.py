"""sportsbook Celery tasks — scheduled reconciliation entry points."""
from __future__ import annotations

from celery import shared_task

from .recovery import RecoveryManager


@shared_task(name='apps.sportsbook.tasks.reconcile_orphaned_bets')
def reconcile_orphaned_bets(dry_run: bool = False) -> dict:
    return RecoveryManager(dry_run=dry_run).run().model_dump(mode='json')
