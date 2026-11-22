"""Aviator house edge by time: a rotation (the edge steps through a list every
N minutes) or time-of-day / day-of-week windows.

The edge in force is decided only by the clock (in the players' time zone):
never by results, the house's takings or who is playing. open_round() asks for
it once, before any bet, stores it on the round and publishes it with the
round, so a player can verify every crash point with that round's own edge.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from datetime import timezone as dt_timezone
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


# -- rotation ------------------------------------------------------------------------

MAX_ROTATION_VALUES = 24


def parse_rotation(raw: str) -> list[Decimal]:
    """'5,10,15' → [5.00, 10.00, 15.00]. ValueError with the reason if any is bad."""
    from decimal import InvalidOperation
    out = []
    for part in (raw or '').replace(';', ',').split(','):
        part = part.strip().rstrip('%')
        if not part:
            continue
        try:
            v = Decimal(part).quantize(Decimal('0.01'))
        except InvalidOperation as exc:
            raise ValueError(f'“{part}” is not a percentage.') from exc
        if not Decimal('0') <= v <= Decimal('50'):
            raise ValueError('Every house edge in the rotation must be between 0% and 50%.')
        out.append(v)
    if not out:
        raise ValueError('List at least one house edge for the rotation.')
    if len(out) > MAX_ROTATION_VALUES:
        raise ValueError(f'A rotation holds at most {MAX_ROTATION_VALUES} values.')
    return out


def parse_steps(raw) -> list[dict]:
    """Validate [{"edge": 5, "on": true}, …] (a plain list of numbers means all on).
    Returns [{"edge": "5.00", "on": True}, …]; ValueError with the reason."""
    if isinstance(raw, str):
        return [{'edge': str(v), 'on': True} for v in parse_rotation(raw)]
    if not isinstance(raw, list) or not raw:
        raise ValueError('List at least one house edge for the rotation.')
    if len(raw) > MAX_ROTATION_VALUES:
        raise ValueError(f'A rotation holds at most {MAX_ROTATION_VALUES} values.')
    out = []
    for step in raw:
        edge, on = (step.get('edge'), step.get('on', True)) if isinstance(step, dict) else (step, True)
        [value] = parse_rotation(str(edge))
        out.append({'edge': str(value), 'on': bool(on)})
    return out


def active_values(cfg: JetSettings) -> list[Decimal]:
    """The edges the rotation steps through: the ones switched on, in order."""
    try:
        steps = parse_steps(cfg.edge_rotation_steps)
    except ValueError:
        return []
    return [Decimal(st['edge']) for st in steps if st['on']]


def rotation_slot(when: datetime, cfg: JetSettings) -> tuple[int, Decimal, datetime]:
    """(position among the active edges, edge, when this slot ends). Counted from
    a fixed point in time, so every server and every restart agree on the slot.
    ValueError when no edge is switched on."""
    values = active_values(cfg)
    if not values:
        raise ValueError('No house edge in the rotation is switched on.')
    step = max(1, cfg.edge_rotation_minutes) * 60
    n = int(when.timestamp() // step)
    ends = datetime.fromtimestamp((n + 1) * step, tz=when.tzinfo or dt_timezone.utc)
    return n % len(values), values[n % len(values)], ends


def current(when: Optional[datetime] = None, *, cfg: Optional[JetSettings] = None) -> tuple[Decimal, str]:
    """(house edge %, what set it: '' = the standard edge). Rotation first, then
    the time windows, then the standard edge."""
    cfg = cfg or JetSettings.load()
    when = when or timezone.now()
    if cfg.edge_rotation_enabled:
        try:
            i, edge, _ = rotation_slot(when, cfg)
            return edge, f'Rotation {edge.normalize():f}% ({i + 1}/{len(active_values(cfg))})'
        except ValueError:
            pass                                    # every edge switched off: the windows / standard edge apply
    edge, rule = edge_at(when, cfg=cfg)
    return edge, (rule.name or str(rule)) if rule else ''


def upcoming(now: Optional[datetime] = None, *, cfg: Optional[JetSettings] = None) -> Optional[dict]:
    """The next change of the edge in force (rotation or windows)."""
    cfg = cfg or JetSettings.load()
    now = now or timezone.now()
    if cfg.edge_rotation_enabled:
        try:
            _, edge, ends = rotation_slot(now, cfg)
        except ValueError:
            return next_change(now, cfg=cfg)
        nxt, label = current(ends, cfg=cfg)
        return {'at': timezone.localtime(ends, tz()).isoformat(), 'house_edge_percent': str(nxt), 'rule': label}
    return next_change(now, cfg=cfg)
