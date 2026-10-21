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
    """Live scores: poll api-football for in-play fixtures (score, clock,
    status) every SPORTSBOOK_LIVE_SCORES_INTERVAL seconds, skipping the call
    while nothing could be live. No-op if API_FOOTBALL_KEY unset."""
    return services.sync_live_fixtures()


@shared_task(name='apps.sportsbook.tasks.sync_fixture_odds')
def sync_fixture_odds() -> int:
    """Refresh odds + markets for upcoming fixtures (per configured league, or
    today and the next API_FOOTBALL_ODDS_DAYS days) and apply them to linked,
    still-open events. No-op if API_FOOTBALL_KEY unset."""
    return services.sync_upcoming_odds()


@shared_task(name='apps.sportsbook.tasks.import_upcoming_fixtures')
def import_upcoming_fixtures() -> int:
    """Pull upcoming fixtures from api-football and create an Event for any
    that aren't linked yet — this is what actually populates the sportsbook
    with bettable events; sync_live_fixtures/sync_fixture_odds only keep
    already-linked events up to date.

    If API_FOOTBALL_LEAGUES is configured, only those leagues are imported
    (each using the shared API_FOOTBALL_SEASON). Otherwise every league
    api-football currently has an active season for is auto-discovered and
    imported, each with its own season year. No-op if API_FOOTBALL_KEY is
    unset."""
    from django.conf import settings
    leagues = getattr(settings, 'API_FOOTBALL_LEAGUES', [])
    season = getattr(settings, 'API_FOOTBALL_SEASON', None)
    next_count = getattr(settings, 'API_FOOTBALL_IMPORT_NEXT', 20)
    if not leagues:
        return services.import_all_current_leagues(next_count=next_count)
    total = 0
    for league in leagues:
        total += services.sync_provider_events(league=league, season=season, next_count=next_count)
    return total


@shared_task(name='apps.sportsbook.tasks.settle_finished_fixtures')
def settle_finished_fixtures() -> int:
    """Settle recently finished fixtures end to end: 1X2, score markets, and
    corners/cards/goalscorer markets once api-football publishes the match
    statistics and events. The live poll can't do this on its own because a
    fixture drops out of `live=all` as soon as it finishes. Retries every run
    until everything on the fixture is settled (bounded to the last few days).
    No-op if API_FOOTBALL_KEY is unset."""
    return services.settle_finished_fixtures()


@shared_task(name='apps.sportsbook.tasks.sync_live_odds')
def sync_live_odds() -> int:
    """In-play: refresh live prices/suspensions every few seconds, then resolve
    in-play bets whose acceptance delay has passed. No-op unless
    SPORTSBOOK_LIVE_BETTING is on (and skips the API call when nothing is live)."""
    fetched = services.sync_live_odds()
    services.confirm_accepting_bets()
    return fetched


@shared_task(name='apps.sportsbook.tasks.confirm_live_bet')
def confirm_live_bet(kind: str, obj_id: int) -> str:
    """Accept or reject one in-play bet ('bet') or multiple ('slip') after the
    acceptance delay. Still ACCEPTING (feed not refreshed yet) is left for the
    sync_live_odds sweep."""
    return services.confirm_live_bet(kind, obj_id)


@shared_task(name='apps.sportsbook.tasks.auto_resolve_markets')
def auto_resolve_markets() -> dict:
    """Backstop so every market on a finished match gets settled: a final pass
    from the match facts, then anything still undecidable is voided (refunded)
    after SPORTSBOOK_AUTO_VOID_AFTER_HOURS; matches never played are voided after
    SPORTSBOOK_UNPLAYED_VOID_HOURS. Works for manually-scored events too."""
    return services.auto_resolve_markets()


@shared_task(name='apps.sportsbook.tasks.clear_old_matches')
def clear_old_matches() -> dict:
    """Hourly housekeeping: close matches long past kick-off and delete old ones
    nobody bet on (see services.clear_old_matches)."""
    return services.clear_old_matches()


@shared_task(name='apps.sportsbook.tasks.check_overdue_live_matches')
def check_overdue_live_matches() -> dict:
    """Every 2 min: ask the provider about matches still marked live after they
    should be over, apply full time, end the hopeless ones as NR
    (see services.check_overdue_live_matches)."""
    return services.check_overdue_live_matches()
