"""Parse api-football "bets" (one bookmaker's markets for a fixture) into normalised
markets. Pure: NO model imports — services.py upserts the result.

Each api-football bet type maps to a settlement kind (settlement.py), a display
group, and a period. Bet types that carry several lines in one list ("Over 2.5",
"Under 2.5", "Over 3.5"…) are split into one market per line. Bet types we can't
settle from the score (corners, cards, scorers…) come through as MANUAL markets
for an operator to settle, when `include_manual` is set.
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
})
_highest_half = _one_of({
    '1st half': ('1h', '1st half'), '2nd half': ('2h', '2nd half'), 'draw': ('draw', 'Equal'),
})


def _over_under(value: str) -> Parsed:
    m = re.fullmatch(rf'(over|under)\s+{_NUM}', value.strip(), re.I)
    if not m:
        return None
    line = _dec(m.group(2))
    if line is None:
        return None
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
}

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
        spec = SPECS.get(name)
        if spec is None:
            if not include_manual:
                continue
            spec = _Spec('manual', 'specials', 'ft', name[:120], _generic)
        base_order = (_SPEC_ORDER.get(name, len(SPECS)) + 1) * 100

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
            if len(outcomes) < 2 and spec.kind != 'manual':
                continue  # a one-sided line can't be offered sensibly
            if spec.split_lines and line is not None:
                shown = format(line.normalize(), 'f') if spec.kind.endswith('over_under') else _fmt_line(line)
                display = f'{spec.name} {shown}'
            else:
                display = spec.name
            base_key = spec.kind if spec.kind != 'manual' else f'manual:{_slug(name)}'
            key = f'{base_key}:{spec.period}' + (f':{line}' if line is not None else '')
            markets.append(FeedMarketData(
                key=key[:80], name=display[:120], group=spec.group, kind=spec.kind,
                period=spec.period, line=line, sort_order=base_order + line_index,
                outcomes=outcomes,
            ))
    return markets
