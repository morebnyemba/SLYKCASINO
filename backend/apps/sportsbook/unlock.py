"""Reopen every market and betting option on every upcoming and live match.

Used by the deploy migration, `manage.py unlock_markets` and the admin's
"Unlock every market now" button. The models are passed in so the migration can
hand it its historical ones. Nothing finished, voided, postponed or past the
lock minute is touched, and outcomes already settled stay settled.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Callable, Optional

from django.db.models import Q
from django.utils import timezone

UPCOMING = ('', 'NS', 'TBD')
IN_PLAY = ('1H', 'HT', '2H')
DEFAULT_LOCK_MINUTE = 75
WALL_CLOCK_ALLOWANCE = timedelta(minutes=18)


def unlock_markets(*, Event, Market, MarketOutcome, lock_minute: int = DEFAULT_LOCK_MINUTE,
                   after_live: Optional[Callable] = None, now=None) -> dict:
    """Returns counts: events reopened, holds cleared, markets and outcomes reopened."""
    now = now or timezone.now()
    report = {'events': 0, 'holds_cleared': 0, 'markets': 0, 'outcomes': 0}

    upcoming = Event.objects.filter(status__in=UPCOMING).filter(Q(starts_at__isnull=True) | Q(starts_at__gt=now))
    live = Event.objects.filter(status__in=IN_PLAY, live_locked_at__isnull=True)
    if lock_minute:
        live = live.exclude(starts_at__lte=now - timedelta(minutes=lock_minute) - WALL_CLOCK_ALLOWANCE)

    for events in (upcoming, live):
        ids = list(events.values_list('id', flat=True))
        if not ids:
            continue
        report['events'] += Event.objects.filter(pk__in=ids, is_open=False).update(is_open=True)
        report['markets'] += Market.objects.filter(event_id__in=ids, settled=False, is_open=False).update(is_open=True)
        report['outcomes'] += MarketOutcome.objects.filter(
            market__event_id__in=ids, market__settled=False, is_open=False, result='pending', odds__gt=Decimal('1'),
        ).update(is_open=True)

    held = live.exclude(live_hold_reason='')
    report['holds_cleared'] = held.update(live_hold_reason='', live_hold_at=None)
    if after_live is not None:
        for event in live:
            after_live(event)
    return report
