"""Short names for picks, the way they read on a combined ticket:
"Liverpool Win", "Draw", "BTTS YES", "Over 2.5 Goals", "Liverpool Over 1.5 Goals",
"Over 8.5 Corners", "Salah Anytime Goalscorer". Several picks from one match join
with " & ": "Liverpool Win & BTTS YES"."""
from __future__ import annotations

import re
from typing import Optional

METRIC = {'goals': 'Goals', 'corners': 'Corners', 'cards': 'Cards'}


def _teams(event, fallback_name: str = '') -> tuple[str, str]:
    home = event.home_team.name if event is not None and getattr(event, 'home_team_id', None) else ''
    away = event.away_team.name if event is not None and getattr(event, 'away_team_id', None) else ''
    if not (home and away):
        name = event.name if event is not None else fallback_name
        parts = re.split(r'\s+vs?\.?\s+', name or '', maxsplit=1, flags=re.IGNORECASE)
        home, away = (parts + ['', ''])[:2] if len(parts) == 2 else (name, '')
    return home or 'Home', away or 'Away'


def _line(v) -> str:
    return format(v.normalize(), 'f') if v is not None else ''


def name(*, event, selection: Optional[str] = None, market=None, outcome=None, fallback: str = '') -> str:
    home, away = _teams(event, fallback)
    if market is None or outcome is None:                       # the headline 1X2
        return {'home': f'{home} Win', 'away': f'{away} Win', 'draw': 'Draw'}.get(selection or '', fallback or 'Pick')
    kind, key, label, line = market.kind, outcome.key, outcome.label, market.line
    metric = METRIC.get(market.metric, 'Goals')
    half = {'1h': '1st Half ', '2h': '2nd Half '}.get(market.period, '')
    if kind == 'match_result' and market.metric == 'goals':
        return f'{half}' + {'home': f'{home} Win', 'away': f'{away} Win', 'draw': 'Draw'}.get(key, label)
    if kind == 'btts':
        return f'{half}BTTS {"YES" if key == "yes" else "NO"}'
    if kind == 'over_under' and key in ('over', 'under'):
        return f'{half}{key.title()} {_line(line)} {metric}'
    if kind in ('home_over_under', 'away_over_under') and key in ('over', 'under'):
        team = home if kind.startswith('home') else away
        return f'{half}{team} {key.title()} {_line(line)} {metric}'
    if kind == 'double_chance':
        return {'1x': f'{home} or Draw', '12': f'{home} or {away}', 'x2': f'Draw or {away}'}.get(key, label)
    if kind == 'draw_no_bet':
        return f'{home if key == "home" else away} (Draw No Bet)'
    if kind in ('anytime_scorer', 'first_scorer', 'last_scorer'):
        return f'{label} {dict(anytime_scorer="Anytime", first_scorer="First", last_scorer="Last")[kind]} Goalscorer'
    if kind == 'correct_score':
        return f'Correct Score {label}'
    if market.metric in ('corners', 'cards') and key in ('over', 'under') and line is not None:
        return f'{half}{key.title()} {_line(line)} {metric}'
    return f'{market.name}: {label}'


def for_leg(leg) -> str:
    """A placed Bet or BetLeg."""
    o = getattr(leg, 'outcome_ref', None)
    return name(event=getattr(leg, 'event_ref', None), selection=getattr(leg, 'selection', None),
                market=o.market if o else None, outcome=o, fallback=(leg.event or '').split(' — ')[0])
