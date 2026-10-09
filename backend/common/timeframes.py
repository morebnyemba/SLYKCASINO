"""Reporting windows shared by the analytics screens — pure, NO model imports.

A timeframe resolves to a half-open window [start, end) plus the bucket size
its chart uses. `all` is the maximum range (start=None: from the very first
record); its chart starts at `earliest` when the caller knows it.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Optional

from django.utils import timezone

FRAMES = {
    'live': 'Last hour',
    'today': 'Today',
    'yesterday': 'Yesterday',
    '7d': 'Last 7 days',
    '30d': 'Last 30 days',
    '90d': 'Last 90 days',
    'this_month': 'This month',
    'last_month': 'Last month',
    'this_year': 'This year',
    'all': 'All time',
    'custom': 'Custom range',
}
BUCKETS = ('minute', 'hour', 'day', 'month')


class TimeframeError(ValueError):
    """An unknown frame or an unusable custom range."""


@dataclass(frozen=True)
class Window:
    frame: str
    label: str
    start: Optional[datetime]   # None = since the beginning
    end: datetime
    bucket: str
    chart_start: Optional[datetime]  # where the chart's first bucket begins


def _midnight(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min))


def _bucket_for(span: timedelta) -> str:
    if span <= timedelta(hours=2):
        return 'minute'
    if span <= timedelta(days=2):
        return 'hour'
    if span <= timedelta(days=93):
        return 'day'
    return 'month'


def parse_day(text: Optional[str]) -> Optional[date]:
    if not text:
        return None
    try:
        return date.fromisoformat(str(text)[:10])
    except ValueError as exc:
        raise TimeframeError(f'bad date: {text}') from exc


def resolve(
    frame: Optional[str] = None, *, start: Optional[str] = None, end: Optional[str] = None,
    now: Optional[datetime] = None, earliest: Optional[datetime] = None,
) -> Window:
    """Turn a frame name (or a custom from/to date pair, inclusive days) into a window."""
    frame = (frame or 'today').lower()
    if frame not in FRAMES:
        raise TimeframeError(f'unknown timeframe: {frame}')
    now = now or timezone.now()
    today = timezone.localdate(now)
    label = FRAMES[frame]

    if frame == 'live':
        s, e = now - timedelta(hours=1), now
    elif frame == 'today':
        s, e = _midnight(today), now
    elif frame == 'yesterday':
        s, e = _midnight(today - timedelta(days=1)), _midnight(today)
    elif frame in ('7d', '30d', '90d'):
        s, e = _midnight(today - timedelta(days=int(frame[:-1]) - 1)), now
    elif frame == 'this_month':
        s, e = _midnight(today.replace(day=1)), now
    elif frame == 'last_month':
        first = today.replace(day=1)
        prev = (first - timedelta(days=1)).replace(day=1)
        s, e = _midnight(prev), _midnight(first)
    elif frame == 'this_year':
        s, e = _midnight(today.replace(month=1, day=1)), now
    elif frame == 'all':
        week_ago = _midnight(today - timedelta(days=6))
        chart_start = min(earliest, week_ago) if earliest else _midnight(today - timedelta(days=29))
        span = now - chart_start
        return Window(frame, label, None, now, _bucket_for(max(span, timedelta(days=3))), chart_start)
    else:  # custom
        first, last = parse_day(start), parse_day(end)
        if first is None or last is None:
            raise TimeframeError('a custom range needs both a start and an end date')
        if last < first:
            first, last = last, first
        if (last - first).days > 3660:
            raise TimeframeError('custom ranges are limited to ten years')
        s, e = _midnight(first), min(_midnight(last + timedelta(days=1)), now)
        label = f'{first.isoformat()} – {last.isoformat()}'
    return Window(frame, label, s, e, _bucket_for(e - s), s)


def bucket_starts(window: Window) -> list[datetime]:
    """Every bucket start in the window's chart, so empty buckets show as zero."""
    start = window.chart_start
    if start is None:
        return []
    out: list[datetime] = []
    if window.bucket == 'minute':
        cur = start.replace(second=0, microsecond=0)
        step = timedelta(minutes=1)
    elif window.bucket == 'hour':
        cur = start.replace(minute=0, second=0, microsecond=0)
        step = timedelta(hours=1)
    elif window.bucket == 'day':
        cur = _midnight(timezone.localdate(start))
        step = timedelta(days=1)
    else:
        local = timezone.localdate(start)
        cur = _midnight(local.replace(day=1))
        while cur < window.end and len(out) < 600:
            out.append(cur)
            d = timezone.localdate(cur)
            cur = _midnight(date(d.year + (d.month == 12), d.month % 12 + 1, 1))
        return out
    while cur < window.end and len(out) < 2000:
        out.append(cur)
        cur += step
    return out


def bucket_key(moment: datetime, bucket: str) -> str:
    """The bucket a timestamp falls in, as the ISO string of its start."""
    local = timezone.localtime(moment) if timezone.is_aware(moment) else moment
    if bucket == 'minute':
        local = local.replace(second=0, microsecond=0)
    elif bucket == 'hour':
        local = local.replace(minute=0, second=0, microsecond=0)
    elif bucket == 'day':
        local = local.replace(hour=0, minute=0, second=0, microsecond=0)
    else:
        local = local.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    return local.isoformat()
