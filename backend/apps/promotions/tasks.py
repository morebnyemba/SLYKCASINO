"""promotions Celery tasks — scheduled reconciliation entry points."""
from __future__ import annotations

from celery import shared_task

from .recovery import RecoveryManager


@shared_task(name='apps.promotions.tasks.reconcile_wagering')
def reconcile_wagering(dry_run: bool = False) -> dict:
    return RecoveryManager(dry_run=dry_run).run().model_dump(mode='json')


@shared_task(name='apps.promotions.tasks.run_bulk_grant')
def run_bulk_grant(grant_id: int) -> str:
    """Work through a bulk bonus grant (promotions.bulk). Safe to run twice."""
    from . import bulk
    return bulk.run(grant_id).status
