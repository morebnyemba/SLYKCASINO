"""The feed manager: one place that decides when the sportsbook may call
api-football, so the daily request quota lasts until it resets (00:00 UTC).

Every request the client makes goes through `before_request` / `after_request`:
it is counted against the day, the provider's own count of what's left (the
`x-ratelimit-requests-*` headers it sends back) is stored, and once only the
reserve is left, only critical fetches (settling bets, an operator's manual
check) may still call.

Every scheduled fetch runs inside `job(kind)`, which says whether it's due:

    interval = max(base interval, cost per run x time left today / (share x quota left))

where each kind's slice of what's left is shared out by "water-filling": what
every kind would need for the rest of the day at its base interval is worked
out; kinds that need less than their weighted share get exactly that, and the
rest goes to the hungry ones (the live polls) by weight. On a quiet day every
base interval applies; on a busy one the polls stretch out automatically
instead of the quota running out at 18:00. The base
intervals already match how often api-football refreshes each endpoint (live
odds every few seconds, live scores 15s, pre-match odds every 3 hours), and live
scores relax to once a minute while the live odds feed (which carries the score
and clock) is flowing.

State lives in the database (FeedQuotaDay, FeedJob) so the web process and the
Celery workers share it.
"""
from __future__ import annotations

import contextvars
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone as dt_timezone
from typing import Iterator, Optional

from django.conf import settings
from django.db.models import F
from django.utils import timezone

PROVIDER = 'api-football'


@dataclass(frozen=True)
class Kind:
    label: str
    base: float          # seconds between runs on a quiet day
    share: float         # most of the remaining quota this kind may plan to use
    critical: bool = False


def _setting(name: str, default: float) -> float:
    try:
        return float(getattr(settings, name, default))
    except (TypeError, ValueError):
        return default


def kinds() -> dict[str, Kind]:
    return {
        'live_odds': Kind('In-play odds', _setting('SPORTSBOOK_LIVE_ODDS_INTERVAL', 10), 0.30),
        'live_scores': Kind('Live scores', _setting('SPORTSBOOK_LIVE_SCORES_INTERVAL', 20), 0.22),
        'odds': Kind('Pre-match odds (today, tomorrow)', _setting('API_FOOTBALL_ODDS_INTERVAL', 3600), 0.15),
        'odds_ahead': Kind('Pre-match odds (later days)', _setting('API_FOOTBALL_ODDS_AHEAD_INTERVAL', 6 * 3600), 0.05),
        'import': Kind('Import upcoming fixtures', _setting('API_FOOTBALL_IMPORT_INTERVAL', 3 * 3600), 0.05),
        'settle': Kind('Settle finished matches', 180, 0.10, critical=True),
        'overdue': Kind('Matches overdue for full time', 120, 0.05, critical=True),
        'manual': Kind('Operator actions', 0, 0.0, critical=True),
    }


# While the live odds feed has priced something this recently, it is keeping
# scores and clocks current, so the live scores poll only has to catch what it
# leaves out (full time, matches with no live prices).
LIVE_SCORES_RELAXED = 60.0
LIVE_ODDS_FRESH = timedelta(seconds=60)

_current = contextvars.ContextVar('feed_kind', default='manual')


class QuotaHold(Exception):
    """A request the manager won't let through (the quota is down to the reserve)."""


# -- the day ------------------------------------------------------------------------

def provider_day(now: Optional[datetime] = None):
    """api-football's quota day (it resets at 00:00 UTC)."""
    return (now or timezone.now()).astimezone(dt_timezone.utc).date()


def seconds_left_today(now: Optional[datetime] = None) -> float:
    now = (now or timezone.now()).astimezone(dt_timezone.utc)
    reset = datetime.combine(now.date() + timedelta(days=1), datetime.min.time(), tzinfo=dt_timezone.utc)
    return max((reset - now).total_seconds(), 60.0)


def _today(now=None):
    from .models import FeedQuotaDay
    row, _ = FeedQuotaDay.objects.get_or_create(provider=PROVIDER, day=provider_day(now))
    return row


def daily_limit(row=None) -> int:
    row = row or _today()
    return int(row.limit or _setting('API_FOOTBALL_DAILY_LIMIT', 7500))


def remaining(row=None) -> int:
    """Requests left today: the provider's own figure when it has told us,
    less what we've sent since; otherwise the limit less what we've counted."""
    row = row or _today()
    if row.remaining is not None:
        return row.remaining
    return daily_limit(row) - row.used


def reserve(row=None) -> int:
    """Kept back for critical fetches (settling bets, operator checks)."""
    return int(daily_limit(row) * _setting('API_FOOTBALL_RESERVE_PERCENT', 5) / 100)


# -- every request ------------------------------------------------------------------

def current_kind() -> str:
    return _current.get()


def before_request(kind: Optional[str] = None) -> None:
    """Raise QuotaHold if this request mustn't go out."""
    kind = kind or current_kind()
    spec = kinds().get(kind, kinds()['manual'])
    row = _today()
    left = remaining(row)
    if left <= 0:
        raise QuotaHold('api-football request quota used up for today')
    if not spec.critical and left <= reserve(row):
        raise QuotaHold('api-football quota down to the reserve kept for settling bets')


def after_request(response=None, kind: Optional[str] = None) -> None:
    """Count a request and store what the provider says is left."""
    from .models import FeedJob, FeedQuotaDay
    kind = kind or current_kind()
    now = timezone.now()
    day = provider_day(now)
    row = _today(now)
    updates: dict = {'used': F('used') + 1}
    headers = getattr(response, 'headers', None) or {}
    left, limit = headers.get('x-ratelimit-requests-remaining'), headers.get('x-ratelimit-requests-limit')
    left = left if isinstance(left, (str, int)) else None          # ignore anything that isn't a real header
    limit = limit if isinstance(limit, (str, int)) else None
    try:
        if left is not None:
            updates.update(remaining=int(left), remaining_at=now)
        elif row.remaining is not None:
            updates['remaining'] = F('remaining') - 1
        if limit is not None:
            updates['limit'] = int(limit)
    except (TypeError, ValueError):
        pass
    FeedQuotaDay.objects.filter(pk=row.pk).update(**updates)
    job_row = _job_row(kind, day)
    FeedJob.objects.filter(pk=job_row.pk).update(requests_today=F('requests_today') + 1)


# -- scheduled jobs -----------------------------------------------------------------

def _job_row(kind: str, day=None):
    from .models import FeedJob
    day = day or provider_day()
    row, _ = FeedJob.objects.get_or_create(kind=kind)
    if row.day != day:
        FeedJob.objects.filter(pk=row.pk).update(day=day, runs_today=0, skipped_today=0, requests_today=0)
        row.refresh_from_db()
    return row


def _live_odds_flowing(now) -> bool:
    from .models import Event
    return Event.objects.filter(live_odds_at__gte=now - LIVE_ODDS_FRESH).exists()


def _base(kind: str, now, flowing: Optional[bool] = None) -> float:
    base = kinds()[kind].base
    if kind == 'live_scores' and (flowing if flowing is not None else _live_odds_flowing(now)):
        base = max(base, LIVE_SCORES_RELAXED)
    return base


def allocation(*, now=None, row=None) -> dict[str, float]:
    """Requests each paced kind may still spend today (water-filling by share
    over what's left above the reserve)."""
    from .models import FeedJob
    now = now or timezone.now()
    row = row or _today(now)
    budget = float(remaining(row) - reserve(row))
    paced = {k: spec for k, spec in kinds().items() if not spec.critical and spec.share > 0}
    if budget <= 0:
        return {k: 0.0 for k in paced}
    costs = dict(FeedJob.objects.filter(kind__in=paced).values_list('kind', 'cost'))
    left = seconds_left_today(now)
    flowing = _live_odds_flowing(now)
    demand = {k: max(costs.get(k, 1.0), 0.5) * left / max(_base(k, now, flowing), 1.0) for k in paced}
    alloc: dict[str, float] = {}
    hungry = set(paced)
    while hungry:
        weight = sum(paced[k].share for k in hungry)
        fair = {k: budget * paced[k].share / weight for k in hungry}
        satisfied = {k for k in hungry if demand[k] <= fair[k]}
        if not satisfied:
            alloc.update(fair)
            break
        for k in satisfied:
            alloc[k] = demand[k]
            budget -= demand[k]
        hungry -= satisfied
    return alloc


def interval(kind: str, *, now=None, row=None, job_row=None) -> Optional[float]:
    """Seconds this kind should wait between runs right now (None: hold until
    tomorrow — nothing left for it)."""
    now = now or timezone.now()
    spec = kinds()[kind]
    base = _base(kind, now)
    if spec.critical or spec.share <= 0:
        return base
    row = row or _today(now)
    alloc = allocation(now=now, row=row).get(kind, 0.0)
    if alloc <= 0:
        return None
    job_row = job_row or _job_row(kind, provider_day(now))
    cost = max(job_row.cost, 0.5)
    # Rounded: an allocation sized to exactly the base need must give the base back, not base + 1e-12.
    return max(base, round(cost * seconds_left_today(now) / alloc, 3))


def due(kind: str, *, now=None) -> bool:
    from .models import FeedJob
    now = now or timezone.now()
    job_row = _job_row(kind, provider_day(now))
    wait = interval(kind, now=now, job_row=job_row)
    if wait != job_row.planned_interval:
        FeedJob.objects.filter(pk=job_row.pk).update(planned_interval=wait)
    if wait is None:
        return False
    # A beat tick a moment early still counts (ticks and intervals line up).
    return job_row.last_run_at is None or (now - job_row.last_run_at).total_seconds() >= wait - 1


@contextmanager
def job(kind: str, *, force: bool = False) -> Iterator[bool]:
    """Run a scheduled fetch if it's due: `with job('odds') as go: if go: ...`.
    Requests made inside are counted against this kind, and its cost per run
    (a moving average) is updated so the pacing knows what a run costs."""
    from .models import FeedJob
    now = timezone.now()
    job_row = _job_row(kind, provider_day(now))
    if not force and not due(kind, now=now):
        FeedJob.objects.filter(pk=job_row.pk).update(skipped_today=F('skipped_today') + 1)
        yield False
        return
    before = job_row.requests_today
    token = _current.set(kind)
    try:
        yield True
    finally:
        _current.reset(token)
        job_row.refresh_from_db()
        spent = max(job_row.requests_today - before, 0) if job_row.day == provider_day(now) else 0
        FeedJob.objects.filter(pk=job_row.pk).update(
            last_run_at=now, runs_today=F('runs_today') + 1,
            # Only runs that called count towards the cost: a live poll that found
            # nothing live costs nothing and shouldn't make the next one look cheap.
            cost=(0.7 * job_row.cost + 0.3 * spent) if spent else job_row.cost,
        )


# -- for the operator console ----------------------------------------------------------

def status(*, now=None) -> dict:
    from .models import FeedJob
    now = now or timezone.now()
    row = _today(now)
    jobs = {j.kind: j for j in FeedJob.objects.all()}
    today = provider_day(now)
    out = []
    for kind, spec in kinds().items():
        j = jobs.get(kind)
        fresh = j is not None and j.day == today
        wait = interval(kind, now=now, row=row, job_row=j) if j is not None else spec.base
        out.append({
            'kind': kind, 'label': spec.label, 'critical': spec.critical,
            'base_seconds': spec.base, 'interval_seconds': wait,
            'last_run_at': j.last_run_at if j else None,
            'runs_today': j.runs_today if fresh else 0, 'skipped_today': j.skipped_today if fresh else 0,
            'requests_today': j.requests_today if fresh else 0, 'cost_per_run': round(j.cost, 2) if j else None,
        })
    left = remaining(row)
    spent_seconds = 86400 - seconds_left_today(now)
    projected = int(row.used / spent_seconds * 86400) if spent_seconds > 600 else None
    return {
        'day': today.isoformat(), 'resets_in_seconds': int(seconds_left_today(now)),
        'limit': daily_limit(row), 'used_by_us': row.used, 'remaining': left, 'reserve': reserve(row),
        'remaining_reported_at': row.remaining_at, 'projected_today': projected, 'jobs': out,
    }


# -- what the pacing means for live trading ------------------------------------------

_planned_memo: dict = {'at': 0.0, 'value': None}


def live_odds_stale_seconds() -> int:
    """How long a live price may go unrefreshed before the match is suspended:
    SPORTSBOOK_LIVE_ODDS_STALE, but never less than 2.5 live-odds polls at the
    interval the manager is currently using (so slower polling on a busy day
    doesn't suspend matches between two polls)."""
    import time
    from .models import FeedJob
    base = int(_setting('SPORTSBOOK_LIVE_ODDS_STALE', 60))
    if time.monotonic() - _planned_memo['at'] > 5:
        try:
            _planned_memo['value'] = (FeedJob.objects.filter(kind='live_odds')
                                      .values_list('planned_interval', flat=True).first())
        except Exception:  # noqa: BLE001 — table missing before migrate
            _planned_memo['value'] = None
        _planned_memo['at'] = time.monotonic()
    planned = _planned_memo['value']
    return int(max(base, 2.5 * planned)) if planned else base
