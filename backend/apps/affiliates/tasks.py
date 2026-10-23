"""affiliates Celery tasks."""
from __future__ import annotations

from celery import shared_task

from . import services
from .recovery import RecoveryManager


@shared_task(name='apps.affiliates.tasks.run_commissions')
def run_commissions() -> dict:
    """New CPAs."""
    return services.run_commissions()


@shared_task(name='apps.affiliates.tasks.credit_losing_tickets')
def credit_losing_tickets() -> int:
    """Every minute: agents' share of tickets lost 3+ minutes ago."""
    return services.credit_losing_tickets()


@shared_task(name='apps.affiliates.tasks.reconcile_commission_payouts')
def reconcile_commission_payouts(dry_run: bool = False) -> dict:
    return RecoveryManager(dry_run=dry_run).run().model_dump(mode='json')
