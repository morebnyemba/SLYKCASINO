"""Parse api-football "bets" (one bookmaker's markets for a fixture) into normalised
markets. Pure: NO model imports — services.py upserts the result.

Each api-football bet type maps to a settlement kind (settlement.py), a display
group, and a period. Bet types that carry several lines in one list ("Over 2.5",
"Under 2.5", "Over 3.5"…) are split into one market per line. Bet types we can't
settle from the score (corners, cards, scorers…) come through as MANUAL markets
for an operator to settle, only when `include_manual` is set — every bet type
listed in SPECS settles automatically from the match facts (see settlement.py).
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional


@dataclass(frozen=True)
class FeedOutcome:
    key: str
    label: str
    odds: Decimal
    sort_order: int = 0


@dataclass(frozen=True)
class FeedMarketData:
    key: str
    name: str
    group: str
    kind: str
    period: str
    line: Optional[Decimal]
    sort_order: int
    outcomes: tuple[FeedOutcome, ...]
    metric: str = 'goals'


# -- value parsers: raw api-football value -> (outcome key, label, line | None) ----

Parsed = Optional[tuple[str, str, Optional[Decimal]]]

_NUM = r'([+-]?\d+(?:\.\d+)?)'


def _dec(text: str) -> Optional[Decimal]:
    try:
        return Decimal(text)
    except (InvalidOperation, ValueError):
        return None


def _fmt_line(line: Decimal) -> str:
    text = format(line.normalize(), 'f')
    return f'+{text}' if line > 0 else text


def _one_of(mapping: dict[str, tuple[str, str]]) -> Callable[[str], Parsed]:
    def parse(value: str) -> Parsed:
        hit = mapping.get(value.strip().lower())
        return (hit[0], hit[1], None) if hit else None
    return parse


_three_way = _one_of({'home': ('home', 'Home'), 'draw': ('draw', 'Draw'), 'away': ('away', 'Away')})
_two_way = _one_of({'home': ('home', 'Home'), 'away': ('away', 'Away')})
_yes_no = _one_of({'yes': ('yes', 'Yes'), 'no': ('no', 'No')})
_odd_even = _one_of({'odd': ('odd', 'Odd'), 'even': ('even', 'Even')})
_double_chance = _one_of({
    'home/draw': ('1x', 'Home or draw'), 'home/away': ('12', 'Home or away'),
    'draw/away': ('x2', 'Draw or away'),
    # Live-feed spellings.
    '1x': ('1x', 'Home or draw'), '12': ('12', 'Home or away'), 'x2': ('x2', 'Draw or away'),
    'home or draw': ('1x', 'Home or draw'), 'home or away': ('12', 'Home or away'),
    'draw or away': ('x2', 'Draw or away'),
})
_highest_half = _one_of({
    '1st half': ('1h', '1st half'), '2nd half': ('2h', '2nd half'), 'draw': ('draw', 'Equal'),
})


def _over_under(value: str) -> Parsed:
    m = re.fullmatch(rf'(over|under)\s+{_NUM}', value.strip(), re.I)
    if not m:
        return None
    line = _dec(m.group(2))
    if line is None or (line * 2) % 1 != 0:
        return None  # quarter lines split the stake — not offered
    side = m.group(1).lower()
    return side, f'{side.title()} {format(line.normalize(), "f")}', line


def _asian_handicap(value: str) -> Parsed:
    """'Home -1.5' / 'Away +1.5' -> keyed by the HOME handicap so both sides of a
    line land in the same market. Quarter lines are skipped (they split stakes)."""
    m = re.fullmatch(rf'(home|away)\s*{_NUM}', value.strip(), re.I)
    if not m:
        return None
    side, handicap = m.group(1).lower(), _dec(m.group(2))
    if handicap is None or (handicap * 2) % 1 != 0:
        return None
    home_line = handicap if side == 'home' else -handicap
    return side, f'{side.title()} {_fmt_line(handicap) if handicap else "0"}', home_line


def _handicap_result(value: str) -> Parsed:
    """3-way (European) handicap: 'Home -1' / 'Draw -1' / 'Away -1', the number
    being the handicap applied to the home side. Whole lines only."""
    m = re.fullmatch(rf'(home|draw|away)\s*{_NUM}', value.strip(), re.I)
    if not m:
        return None
    side, line = m.group(1).lower(), _dec(m.group(2))
    if line is None or line % 1 != 0:
        return None
    return side, f'{side.title()} ({_fmt_line(line) if line else "0"})', line


def _correct_score(value: str) -> Parsed:
    m = re.fullmatch(r'(\d+)\s*[:-]\s*(\d+)', value.strip())
    if not m:
        return None
    home, away = int(m.group(1)), int(m.group(2))
    return f'{home}:{away}', f'{home}-{away}', None


def _exact_goals(value: str) -> Parsed:
    text = value.strip().lower()
    if text.isdigit():
        return text, f'{text} goal{"" if text == "1" else "s"}', None
    m = re.fullmatch(r'(?:more|over)\s*(\d+)', text)
    if m:
        # "more 6" = more than six goals.
        n = int(m.group(1)) + 1
        return f'{n}+', f'{n}+ goals', None
    return None


def _ht_ft(value: str) -> Parsed:
    parts = [p.strip().lower() for p in value.split('/')]
    names = {'home': 'Home', 'draw': 'Draw', 'away': 'Away'}
    if len(parts) != 2 or any(p not in names for p in parts):
        return None
    return f'{parts[0]}/{parts[1]}', f'{names[parts[0]]} / {names[parts[1]]}', None


_team_first = _one_of({
    'home': ('home', 'Home'), 'away': ('away', 'Away'),
    # api-football prices "no goal" as the Draw outcome of this market.
    'draw': ('none', 'No goal'), 'no goal': ('none', 'No goal'), 'none': ('none', 'No goal'),
})


def _result_btts(value: str) -> Parsed:
    m = re.fullmatch(r'(home|draw|away)\s*/\s*(yes|no)', value.strip(), re.I)
    if not m:
        return None
    res, btts = m.group(1).lower(), m.group(2).lower()
    return f'{res}/{btts}', f'{res.title()} & {"Yes" if btts == "yes" else "No"}', None


def _result_total(value: str) -> Parsed:
    m = re.fullmatch(rf'(home|draw|away)\s*/\s*(over|under)\s+{_NUM}', value.strip(), re.I)
    if not m:
        return None
    line = _dec(m.group(3))
    if line is None or (line * 2) % 1 != 0:
        return None
    res, side = m.group(1).lower(), m.group(2).lower()
    return f'{res}/{side}', f'{res.title()} & {side.title()} {format(line.normalize(), "f")}', line


def _scorer(value: str) -> Parsed:
    """Goalscorer markets: the value is a player's name (or "No goal")."""
    name = value.strip()
    if not name:
        return None
    if name.lower() in ('no goal', 'no goalscorer', 'no goal scorer', 'none'):
        return 'none', 'No goalscorer', None
    key = re.sub(r'[^a-z0-9]+', '_', name.lower()).strip('_')[:40]
    return (key, name[:80], None) if key else None


def _generic(value: str) -> Parsed:
    """Manual markets: keep the provider's wording, derive a stable key from it."""
    label = value.strip()[:60]
    key = re.sub(r'[^a-z0-9+:.-]+', '_', label.lower()).strip('_')[:24]
    return (key, label, None) if key else None


@dataclass(frozen=True)
class _Spec:
    kind: str
    group: str
    period: str
    name: str
    parse: Callable[[str], Parsed]
    split_lines: bool = False
    metric: str = 'goals'


# Order here is display order (sort_order) within the event page.
SPECS: dict[str, _Spec] = {
    'Double Chance': _Spec('double_chance', 'main', 'ft', 'Double chance', _double_chance),
    'Home/Away': _Spec('draw_no_bet', 'main', 'ft', 'Draw no bet', _two_way),
    'Both Teams Score': _Spec('btts', 'main', 'ft', 'Both teams to score', _yes_no),
    'Goals Over/Under': _Spec('over_under', 'goals', 'ft', 'Total goals', _over_under, True),
    'Exact Goals Number': _Spec('exact_goals', 'goals', 'ft', 'Exact total goals', _exact_goals),
    'Odd/Even': _Spec('odd_even', 'goals', 'ft', 'Total goals odd/even', _odd_even),
    'Total - Home': _Spec('home_over_under', 'teams', 'ft', 'Home team total goals', _over_under, True),
    'Total - Away': _Spec('away_over_under', 'teams', 'ft', 'Away team total goals', _over_under, True),
    'Clean Sheet - Home': _Spec('clean_sheet_home', 'teams', 'ft', 'Home clean sheet', _yes_no),
    'Clean Sheet - Away': _Spec('clean_sheet_away', 'teams', 'ft', 'Away clean sheet', _yes_no),
    'Win to Nil - Home': _Spec('win_to_nil_home', 'teams', 'ft', 'Home to win to nil', _yes_no),
    'Win to Nil - Away': _Spec('win_to_nil_away', 'teams', 'ft', 'Away to win to nil', _yes_no),
    'Asian Handicap': _Spec('asian_handicap', 'handicap', 'ft', 'Asian handicap', _asian_handicap, True),
    'Handicap Result': _Spec('handicap_result', 'handicap', 'ft', 'Handicap result', _handicap_result, True),
    'First Half Winner': _Spec('match_result', 'halves', '1h', '1st half result', _three_way),
    'Second Half Winner': _Spec('match_result', 'halves', '2h', '2nd half result', _three_way),
    'HT/FT Double': _Spec('ht_ft', 'halves', 'ft', 'Half time / full time', _ht_ft),
    'Goals Over/Under First Half': _Spec('over_under', 'halves', '1h', '1st half total goals', _over_under, True),
    'Goals Over/Under - Second Half': _Spec('over_under', 'halves', '2h', '2nd half total goals', _over_under, True),
    'Both Teams Score - First Half': _Spec('btts', 'halves', '1h', '1st half both teams to score', _yes_no),
    'Highest Scoring half': _Spec('highest_scoring_half', 'halves', 'ft', 'Highest scoring half', _highest_half),
    'Exact Score': _Spec('correct_score', 'score', 'ft', 'Correct score', _correct_score),
    'Correct Score - First Half': _Spec('correct_score', 'score', '1h', '1st half correct score', _correct_score),
    'Correct Score - Second Half': _Spec('correct_score', 'score', '2h', '2nd half correct score', _correct_score),
    # Result combos and first/last goal
    'Results/Both Teams Score': _Spec('result_btts', 'main', 'ft', 'Result & both teams to score', _result_btts),
    'Result/Total Goals': _Spec('result_total', 'main', 'ft', 'Result & total goals', _result_total, True),
    'Team To Score First': _Spec('first_team_to_score', 'goals', 'ft', 'Team to score first', _team_first),
    'Team To Score Last': _Spec('last_team_to_score', 'goals', 'ft', 'Team to score last', _team_first),
    'Own Goal': _Spec('own_goal', 'goals', 'ft', 'Own goal in the match', _yes_no),
    'Win To Nil': _Spec('win_to_nil', 'teams', 'ft', 'To win to nil', _two_way),
    'Home Team Score a Goal': _Spec('team_to_score_home', 'teams', 'ft', 'Home team to score', _yes_no),
    'Away Team Score a Goal': _Spec('team_to_score_away', 'teams', 'ft', 'Away team to score', _yes_no),
    'Home Team Exact Goals Number': _Spec('home_exact_goals', 'teams', 'ft', 'Home team exact goals', _exact_goals),
    'Away Team Exact Goals Number': _Spec('away_exact_goals', 'teams', 'ft', 'Away team exact goals', _exact_goals),
    # Half variants
    'Win Both Halves': _Spec('win_both_halves', 'halves', 'ft', 'To win both halves', _two_way),
    'To Win Either Half': _Spec('win_either_half', 'halves', 'ft', 'To win either half', _two_way),
    'To Score In Both Halves By Teams': _Spec('score_both_halves', 'halves', 'ft', 'To score in both halves', _two_way),
    'Double Chance - First Half': _Spec('double_chance', 'halves', '1h', '1st half double chance', _double_chance),
    'Double Chance - Second Half': _Spec('double_chance', 'halves', '2h', '2nd half double chance', _double_chance),
    'Odd/Even - First Half': _Spec('odd_even', 'halves', '1h', '1st half goals odd/even', _odd_even),
    'Odd/Even - Second Half': _Spec('odd_even', 'halves', '2h', '2nd half goals odd/even', _odd_even),
    'Exact Goals Number - First Half': _Spec('exact_goals', 'halves', '1h', '1st half exact goals', _exact_goals),
    'Second Half Exact Goals Number': _Spec('exact_goals', 'halves', '2h', '2nd half exact goals', _exact_goals),
    'Both Teams To Score - Second Half': _Spec('btts', 'halves', '2h', '2nd half both teams to score', _yes_no),
    'Handicap Result - First Half': _Spec('handicap_result', 'halves', '1h', '1st half handicap result', _handicap_result, True),
    'Asian Handicap First Half': _Spec('asian_handicap', 'halves', '1h', '1st half Asian handicap', _asian_handicap, True),
    # Corners (settled from match statistics)
    'Corners 1x2': _Spec('match_result', 'corners', 'ft', 'Corners match result', _three_way, metric='corners'),
    'Corners Over Under': _Spec('over_under', 'corners', 'ft', 'Total corners', _over_under, True, 'corners'),
    'Home Corners Over/Under': _Spec('home_over_under', 'corners', 'ft', 'Home team corners', _over_under, True, 'corners'),
    'Away Corners Over/Under': _Spec('away_over_under', 'corners', 'ft', 'Away team corners', _over_under, True, 'corners'),
    'Corners Asian Handicap': _Spec('asian_handicap', 'corners', 'ft', 'Corners handicap', _asian_handicap, True, 'corners'),
    'Corners Odd/Even': _Spec('odd_even', 'corners', 'ft', 'Total corners odd/even', _odd_even, metric='corners'),
    # Cards (yellow + red per team, from match statistics)
    'Cards 1x2': _Spec('match_result', 'cards', 'ft', 'Most cards', _three_way, metric='cards'),
    'Cards Over/Under': _Spec('over_under', 'cards', 'ft', 'Total cards', _over_under, True, 'cards'),
    'Home Team Total Cards': _Spec('home_over_under', 'cards', 'ft', 'Home team cards', _over_under, True, 'cards'),
    'Away Team Total Cards': _Spec('away_over_under', 'cards', 'ft', 'Away team cards', _over_under, True, 'cards'),
    'Cards Asian Handicap': _Spec('asian_handicap', 'cards', 'ft', 'Cards handicap', _asian_handicap, True, 'cards'),
    'RCARD': _Spec('red_card', 'cards', 'ft', 'Red card in the match', _yes_no),
    # Goalscorers (settled from goal events + lineups)
    'Anytime Goal Scorer': _Spec('anytime_scorer', 'scorers', 'ft', 'Anytime goalscorer', _scorer),
    'First Goal Scorer': _Spec('first_scorer', 'scorers', 'ft', 'First goalscorer', _scorer),
    'Last Goal Scorer': _Spec('last_scorer', 'scorers', 'ft', 'Last goalscorer', _scorer),
}

# Alternate spellings seen across bookmakers in the same feed.
ALIASES = {
    'Both Teams Score - Second Half': 'Both Teams To Score - Second Half',
    'Result/Both Teams Score': 'Results/Both Teams Score',
    'Red Card': 'RCARD',
    'Total Cards': 'Cards Over/Under',
    'Total Corners': 'Corners Over Under',
    'Corners Over/Under': 'Corners Over Under',
    'Goalscorer': 'Anytime Goal Scorer',
    'Anytime Goalscorer': 'Anytime Goal Scorer',
    'First Goalscorer': 'First Goal Scorer',
    'Last Goalscorer': 'Last Goal Scorer',
}

_SPEC_BY_LOWER = {name.lower(): name for name in SPECS}
_SPEC_BY_LOWER.update({alias.lower(): target for alias, target in ALIASES.items()})

# The headline 1X2 lives on Event.odds/odds_draw/odds_away, not as a Market.
SKIP = {'Match Winner'}

_SPEC_ORDER = {name: i for i, name in enumerate(SPECS)}


def _slug(text: str) -> str:
    return re.sub(r'[^a-z0-9]+', '_', text.lower()).strip('_')[:40]


def parse_markets(bets: list[dict[str, Any]], *, include_manual: bool = True) -> list[FeedMarketData]:
    """Normalise a list of api-football bets ({name, values: [{value, odd}]})."""
    markets: list[FeedMarketData] = []
    for bet in bets:
        name = str(bet.get('name') or '').strip()
        if not name or name in SKIP:
            continue
        canonical = _SPEC_BY_LOWER.get(name.lower())
        spec = SPECS.get(canonical) if canonical else None
        if spec is None:
            if not include_manual:
                continue
            spec = _Spec('manual', 'specials', 'ft', name[:120], _generic)
        base_order = (_SPEC_ORDER.get(canonical or name, len(SPECS)) + 1) * 100

        # line -> {outcome key -> FeedOutcome}; None groups line-less markets.
        by_line: dict[Optional[Decimal], dict[str, FeedOutcome]] = {}
        for index, raw in enumerate(bet.get('values') or []):
            parsed = spec.parse(str(raw.get('value', '')))
            odds = _dec(str(raw.get('odd', '')))
            if parsed is None or odds is None or odds <= 1:
                continue
            key, label, line = parsed
            bucket = by_line.setdefault(line if spec.split_lines else None, {})
            bucket.setdefault(key, FeedOutcome(key=key, label=label, odds=odds, sort_order=index))

        lines = sorted(by_line, key=lambda ln: (ln is None, ln if ln is not None else 0))
        for line_index, line in enumerate(lines):
            outcomes = tuple(by_line[line].values())
            if len(outcomes) < 2 and spec.kind not in ('manual', 'anytime_scorer', 'first_scorer', 'last_scorer'):
                continue  # a one-sided line can't be offered sensibly
            if spec.split_lines and line is not None:
                shown = _fmt_line(line) if 'handicap' in spec.kind else format(line.normalize(), 'f')
                display = f'{spec.name} {shown}'
            else:
                display = spec.name
            base_key = spec.kind if spec.kind != 'manual' else f'manual:{_slug(name)}'
            if spec.metric != 'goals':
                base_key = f'{base_key}:{spec.metric}'
            key = f'{base_key}:{spec.period}' + (f':{line}' if line is not None else '')
            markets.append(FeedMarketData(
                key=key[:80], name=display[:120], group=spec.group, kind=spec.kind,
                period=spec.period, line=line, sort_order=base_order + line_index,
                outcomes=outcomes, metric=spec.metric,
            ))
    return markets


# -- in-play (api-football /odds/live) -----------------------------------------

# Live bet types we trade in play, mapped onto the pre-match spec that shares
# their settlement (so a live price updates the same Market row). Only markets
# settled on the whole match (or the half in progress) regardless of when the
# bet was struck: handicaps, "next goal" and rest-of-match markets are left out
# because their in-play rules vary by bookmaker.
LIVE_BETS = {
    'fulltime result': 'Match Winner',
    'match winner': 'Match Winner',
    '1x2': 'Match Winner',
    'double chance': 'Double Chance',
    'draw no bet': 'Home/Away',
    'both teams to score': 'Both Teams Score',
    'both teams score': 'Both Teams Score',
    'over/under line': 'Goals Over/Under',
    'match goals': 'Goals Over/Under',
    'goals over/under': 'Goals Over/Under',
    'total goals': 'Goals Over/Under',
    'goals odd/even': 'Odd/Even',
    'odd/even': 'Odd/Even',
    'final score': 'Exact Score',
    'correct score': 'Exact Score',
    'exact score': 'Exact Score',
    '1x2 - 1st half': 'First Half Winner',
    'half time result': 'First Half Winner',
    'first half winner': 'First Half Winner',
}

# Markets on the first half stop trading once it's over.
FIRST_HALF_ONLY = {'First Half Winner'}


def _live_value(raw: dict[str, Any]) -> Optional[dict[str, Any]]:
    """One live price -> the pre-match value shape ({value, odd}), folding the
    separate `handicap` field into the value ("Over" + 2.5 -> "Over 2.5").
    Suspended prices are dropped, which suspends that outcome."""
    if raw.get('suspended'):
        return None
    value = str(raw.get('value', '')).strip()
    handicap = raw.get('handicap')
    if handicap not in (None, ''):
        value = f'{value} {handicap}'
    return {'value': value, 'odd': raw.get('odd')}


def parse_live_odds(
    odds: list[dict[str, Any]], *, first_half: bool = True,
) -> tuple[Optional[tuple[Decimal, Optional[Decimal], Decimal]], list[FeedMarketData]]:
    """Normalise a live fixture's `odds` list into (1X2 prices or None, markets).
    `first_half=False` drops first-half markets (the half is over)."""
    merged: dict[str, list[dict[str, Any]]] = {}
    winner: list[dict[str, Any]] = []
    for bet in odds or []:
        canonical = LIVE_BETS.get(str(bet.get('name') or '').strip().lower())
        if canonical is None or (canonical in FIRST_HALF_ONLY and not first_half):
            continue
        if canonical == 'Match Winner':
            winner = winner or list(bet.get('values') or [])
            continue
        values = merged.setdefault(canonical, [])
        for raw in bet.get('values') or []:
            value = _live_value(raw)
            if value is not None:
                values.append(value)

    # The headline 1X2 trades as a whole: any leg suspended suspends all three.
    one_x_two = None
    if winner and not any(v.get('suspended') for v in winner):
        prices = {str(v.get('value', '')).strip().lower(): _dec(str(v.get('odd', ''))) for v in winner}
        home = prices.get('home') or prices.get('1')
        draw = prices.get('draw') or prices.get('x')
        away = prices.get('away') or prices.get('2')
        if home and away and draw and min(home, draw, away) > 1:
            one_x_two = (home, draw, away)
    markets = parse_markets(
        [{'name': name, 'values': values} for name, values in merged.items()], include_manual=False,
    )
    return one_x_two, markets
