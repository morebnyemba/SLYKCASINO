"""livechat Celery tasks — scheduled reconciliation entry points."""
from __future__ import annotations

from celery import shared_task

from .recovery import RecoveryManager


@shared_task(name='apps.livechat.tasks.reconcile_undelivered')
def reconcile_undelivered(dry_run: bool = False) -> dict:
    return RecoveryManager(dry_run=dry_run).run().model_dump(mode='json')
