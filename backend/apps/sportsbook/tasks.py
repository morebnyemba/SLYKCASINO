"""sportsbook Celery tasks — scheduled reconciliation entry points."""
from __future__ import annotations

from celery import shared_task

from . import services
from .recovery import RecoveryManager


@shared_task(name='apps.sportsbook.tasks.reconcile_orphaned_bets')
def reconcile_orphaned_bets(dry_run: bool = False) -> dict:
    return RecoveryManager(dry_run=dry_run).run().model_dump(mode='json')


@shared_task(name='apps.sportsbook.tasks.sync_live_fixtures')
def sync_live_fixtures() -> int:
    """Poll api-football for in-play fixtures and settle any linked events
    that have finished since the last poll. No-op if API_FOOTBALL_KEY unset."""
    return services.sync_provider_fixtures(live='all')


@shared_task(name='apps.sportsbook.tasks.sync_fixture_odds')
def sync_fixture_odds() -> int:
    """Poll api-football for today's 1X2 odds and apply them to linked, still
    -open events. No-op if API_FOOTBALL_KEY unset."""
    from datetime import date as date_cls
    return services.sync_provider_odds(date=date_cls.today().isoformat())
