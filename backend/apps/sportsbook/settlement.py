"""sportsbook settlement rules — decide each market outcome from the final score.

Pure functions, NO model imports: callers pass a market's kind/period/line and an
outcome key, plus the match Score, and get back 'won' | 'lost' | 'void', or None
when the outcome can't be decided from the score (manual markets, or the half-time
score is needed but missing).

Outcome keys (normalised by clients.py when importing a feed):
  match_result / draw_no_bet / handicap_result : 'home' | 'draw' | 'away'
  double_chance                                : '1x' | '12' | 'x2'
  *over_under                                  : 'over' | 'under'   (line on market)
  btts / clean_sheet_* / win_to_nil_*          : 'yes' | 'no'
  asian_handicap                               : 'home' | 'away'    (line = home handicap)
  correct_score                                : '<home>:<away>'
  exact_goals                                  : '<n>' or '<n>+' (n or more)
  odd_even                                     : 'odd' | 'even'
  ht_ft                                        : '<ht>/<ft>' with each part home|draw|away
  highest_scoring_half                         : '1h' | '2h' | 'draw'

Quarter-goal Asian lines (e.g. -0.25) split a stake across two lines and can
half-win; the importer skips them, so only whole and half lines reach here.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

WON, LOST, VOID = 'won', 'lost', 'void'


@dataclass(frozen=True)
class Score:
    """Regulation-time score, with the half-time score when known."""

    home: int
    away: int
    ht_home: Optional[int] = None
    ht_away: Optional[int] = None

    @property
    def has_half_time(self) -> bool:
        return self.ht_home is not None and self.ht_away is not None

    def for_period(self, period: str) -> Optional[tuple[int, int]]:
        """(home, away) goals scored in a period: 'ft', '1h' or '2h'."""
        if period == 'ft':
            return self.home, self.away
        if not self.has_half_time:
            return None
        if period == '1h':
            return self.ht_home, self.ht_away  # type: ignore[return-value]
        if period == '2h':
            return self.home - self.ht_home, self.away - self.ht_away  # type: ignore[operator]
        return None


def _result(home: int, away: int) -> str:
    if home > away:
        return 'home'
    if home < away:
        return 'away'
    return 'draw'


def _yes_no(key: str, condition: bool) -> Optional[str]:
    if key == 'yes':
        return WON if condition else LOST
    if key == 'no':
        return LOST if condition else WON
    return None


def _over_under(key: str, total: Decimal, line: Optional[Decimal]) -> Optional[str]:
    if line is None or key not in ('over', 'under'):
        return None
    if total == line:
        return VOID  # whole-number line landing exactly: stake returned
    over = total > line
    return WON if (over if key == 'over' else not over) else LOST


def settle_outcome(
    *, kind: str, period: str, line: Optional[Decimal], key: str, score: Score,
) -> Optional[str]:
    """Settle one outcome. Returns 'won' | 'lost' | 'void', or None if undecidable."""
    goals = score.for_period(period or 'ft')
    if goals is None:
        return None  # needs a half-time score we don't have
    home, away = goals
    total = Decimal(home + away)

    if kind == 'match_result':
        return WON if key == _result(home, away) else LOST

    if kind == 'double_chance':
        res = _result(home, away)
        covers = {'1x': ('home', 'draw'), '12': ('home', 'away'), 'x2': ('draw', 'away')}.get(key)
        if covers is None:
            return None
        return WON if res in covers else LOST

    if kind == 'draw_no_bet':
        res = _result(home, away)
        if res == 'draw':
            return VOID
        return WON if key == res else LOST

    if kind == 'over_under':
        return _over_under(key, total, line)
    if kind == 'home_over_under':
        return _over_under(key, Decimal(home), line)
    if kind == 'away_over_under':
        return _over_under(key, Decimal(away), line)

    if kind == 'btts':
        return _yes_no(key, home > 0 and away > 0)

    if kind == 'asian_handicap':
        if line is None or key not in ('home', 'away'):
            return None
        # `line` is the handicap applied to the home side; away gets the opposite.
        margin = Decimal(home) + line - Decimal(away)
        if margin == 0:
            return VOID
        home_covers = margin > 0
        return WON if (home_covers if key == 'home' else not home_covers) else LOST

    if kind == 'handicap_result':
        if line is None:
            return None
        res = _result(int(Decimal(home) + line), away)
        return WON if key == res else LOST

    if kind == 'correct_score':
        try:
            want_home, want_away = (int(p) for p in key.split(':'))
        except ValueError:
            return None
        return WON if (home, away) == (want_home, want_away) else LOST

    if kind == 'exact_goals':
        if key.endswith('+'):
            try:
                return WON if int(total) >= int(key[:-1]) else LOST
            except ValueError:
                return None
        try:
            return WON if int(total) == int(key) else LOST
        except ValueError:
            return None

    if kind == 'odd_even':
        if key not in ('odd', 'even'):
            return None
        return WON if (int(total) % 2 == 1) == (key == 'odd') else LOST

    if kind == 'ht_ft':
        if not score.has_half_time:
            return None
        ht = _result(score.ht_home, score.ht_away)  # type: ignore[arg-type]
        ft = _result(score.home, score.away)
        return WON if key == f'{ht}/{ft}' else LOST

    if kind == 'highest_scoring_half':
        if not score.has_half_time:
            return None
        first = score.ht_home + score.ht_away  # type: ignore[operator]
        second = score.home + score.away - first
        actual = '1h' if first > second else '2h' if second > first else 'draw'
        return WON if key == actual else LOST

    if kind == 'clean_sheet_home':
        return _yes_no(key, away == 0)
    if kind == 'clean_sheet_away':
        return _yes_no(key, home == 0)
    if kind == 'win_to_nil_home':
        return _yes_no(key, home > away and away == 0)
    if kind == 'win_to_nil_away':
        return _yes_no(key, away > home and home == 0)

    return None  # manual / unknown kinds are settled by an operator
