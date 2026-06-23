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


@shared_task(name='apps.sportsbook.tasks.import_upcoming_fixtures')
def import_upcoming_fixtures() -> int:
    """Pull each configured league's next upcoming fixtures from api-football
    and create an Event for any that aren't linked yet — this is what
    actually populates the sportsbook with bettable events; sync_live_fixtures
    /sync_fixture_odds only keep already-linked events up to date. No-op if
    API_FOOTBALL_KEY or API_FOOTBALL_LEAGUES is unset."""
    from django.conf import settings
    leagues = getattr(settings, 'API_FOOTBALL_LEAGUES', [])
    season = getattr(settings, 'API_FOOTBALL_SEASON', None)
    next_count = getattr(settings, 'API_FOOTBALL_IMPORT_NEXT', 20)
    total = 0
    for league in leagues:
        total += services.sync_provider_events(league=league, season=season, next_count=next_count)
    return total
