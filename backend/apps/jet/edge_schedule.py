"""Aviator house edge by time of day and day of week.

The edge in force is decided only by the clock (in the players' time zone):
never by results, the house's takings or who is playing. open_round() asks for
it once, before any bet, stores it on the round and publishes it with the
round, so a player can verify every crash point with that round's own edge.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from django.utils import timezone

from .models import JetEdgeRule, JetSettings

DAY_NAMES = ('Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun')


def tz() -> ZoneInfo:
    try:
        return ZoneInfo(getattr(settings, 'PLAYER_TIME_ZONE', '') or 'Africa/Harare')
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo('Africa/Harare')


def covers(rule: JetEdgeRule, local: datetime) -> bool:
    """Whether the rule's window includes this local moment. A window ending at
    or before its start runs past midnight and belongs to the day it starts."""
    t, day = local.time().replace(tzinfo=None), local.weekday()
    if rule.starts < rule.ends:
        return str(day) in rule.days and rule.starts <= t < rule.ends
    if rule.starts == rule.ends:                         # all day
        return str(day) in rule.days
    if t >= rule.starts:                                 # evening part, today's window
        return str(day) in rule.days
    return t < rule.ends and str((day - 1) % 7) in rule.days   # small hours, yesterday's window


def edge_at(when: Optional[datetime] = None, *, cfg: Optional[JetSettings] = None,
            rules: Optional[list] = None) -> tuple[Decimal, Optional[JetEdgeRule]]:
    """(house edge %, the rule that set it or None for the standard edge)."""
    cfg = cfg or JetSettings.load()
    if not cfg.edge_schedule_enabled:
        return cfg.house_edge_percent, None
    local = timezone.localtime(when or timezone.now(), tz())
    for rule in rules if rules is not None else JetEdgeRule.objects.filter(enabled=True):
        if rule.enabled and covers(rule, local):
            return rule.house_edge_percent, rule
    return cfg.house_edge_percent, None


def next_change(now: Optional[datetime] = None, *, cfg: Optional[JetSettings] = None) -> Optional[dict]:
    """When the edge in force next changes within a week, and to what."""
    cfg = cfg or JetSettings.load()
    if not cfg.edge_schedule_enabled:
        return None
    zone = tz()
    now = timezone.localtime(now or timezone.now(), zone)
    rules = list(JetEdgeRule.objects.filter(enabled=True))
    current, _ = edge_at(now, cfg=cfg, rules=rules)
    boundaries = set()
    for offset in range(0, 8):
        day: date = (now + timedelta(days=offset)).date()
        for rule in rules:
            for t in (rule.starts, rule.ends, time(0, 0)):
                moment = datetime.combine(day, t, tzinfo=zone)
                if moment > now:
                    boundaries.add(moment)
    for moment in sorted(boundaries):
        edge, rule = edge_at(moment, cfg=cfg, rules=rules)
        if edge != current:
            return {'at': moment.isoformat(), 'house_edge_percent': str(edge), 'rule': rule.name if rule else ''}
    return None


def describe_days(days: str) -> str:
    picked = [i for i in range(7) if str(i) in days]
    if picked == list(range(7)):
        return 'Every day'
    if picked == [0, 1, 2, 3, 4]:
        return 'Weekdays'
    if picked == [5, 6]:
        return 'Weekends'
    return ', '.join(DAY_NAMES[i] for i in picked)
