"""wallet Celery tasks — scheduled reconciliation entry points."""
from __future__ import annotations

from celery import shared_task

from .recovery import RecoveryManager


@shared_task(name='apps.wallet.tasks.reconcile_ledger')
def reconcile_ledger(dry_run: bool = False) -> dict:
    return RecoveryManager(dry_run=dry_run).run().model_dump(mode='json')


@shared_task(name='apps.wallet.tasks.sweep_pending_payments')
def sweep_pending_payments() -> int:
    from .payments import gateway_enabled, sweep_pending
    return sweep_pending() if gateway_enabled() else 0


@shared_task(name='apps.wallet.tasks.expire_idle_bonuses')
def expire_idle_bonuses() -> dict:
    """Hourly: forfeit Bonus wallets unused for the admin's expiry period; warn 3 days before."""
    from . import bonus
    report = bonus.expire_idle()
    return {**report, 'amount': str(report['amount'])}
