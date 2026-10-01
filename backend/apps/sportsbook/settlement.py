"""sportsbook settlement rules — decide each market outcome from the match facts.

Pure functions, NO model imports: callers pass a market's kind/period/line/metric
and an outcome (key + label), plus the match facts (Score), and get back
'won' | 'lost' | 'void', or None when the facts don't decide it (e.g. the
half-time score, corner count or goal events aren't available yet, or a player
name is ambiguous). None leaves the market pending for a retry or an operator.

Facts are regulation time (90' + stoppage): extra-time goals, corners and cards
never count. Corners/cards come from full-match statistics, so they're only
used for matches that didn't go to extra time.

Outcome keys (normalised by market_feed.py when importing a feed):
  match_result / draw_no_bet / handicap_result : 'home' | 'draw' | 'away'
  double_chance                                : '1x' | '12' | 'x2'
  *over_under                                  : 'over' | 'under'   (line on market)
  btts / clean_sheet_* / win_to_nil_* / team_to_score_* / own_goal / red_card : 'yes' | 'no'
  win_to_nil / win_both_halves / win_either_half / score_both_halves : 'home' | 'away'
  asian_handicap                               : 'home' | 'away'    (line = home handicap)
  correct_score                                : '<home>:<away>'
  exact_goals / home_exact_goals / away_exact_goals : '<n>' or '<n>+' (n or more)
  odd_even                                     : 'odd' | 'even'
  ht_ft                                        : '<ht>/<ft>' with each part home|draw|away
  highest_scoring_half                         : '1h' | '2h' | 'draw'
  result_btts                                  : '<home|draw|away>/<yes|no>'
  result_total                                 : '<home|draw|away>/<over|under>'  (line on market)
  first_team_to_score / last_team_to_score     : 'home' | 'away' | 'none'
  anytime_scorer / first_scorer / last_scorer  : a player key (name in the label) or 'none'

Metric: count-based kinds (1X2, totals, handicaps, odd/even…) count goals by
default, or corners / cards (yellow + red per team) when the market says so.

Quarter lines (e.g. -0.25, 2.75) split a stake across two lines and can
half-win; the importer skips them, so only whole and half lines reach here.
"""
from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal
from typing import Optional

WON, LOST, VOID = 'won', 'lost', 'void'


@dataclass(frozen=True)
class GoalEvent:
    """A regulation-time goal. `side` is the team credited with it (for an own
    goal, the team that benefits); `player` is who put it in."""

    minute: int
    side: str
    player: str = ''
    own_goal: bool = False
    penalty: bool = False


@dataclass(frozen=True)
class Score:
    """Everything settlement can use about a finished match. Only the 90-minute
    score is required; the rest is optional and markets needing it stay pending
    until it's known."""

    home: int
    away: int
    ht_home: Optional[int] = None
    ht_away: Optional[int] = None
    corners: Optional[tuple[int, int]] = None
    cards: Optional[tuple[int, int]] = None      # yellow + red, per team
    reds: Optional[tuple[int, int]] = None
    goals: Optional[tuple[GoalEvent, ...]] = None  # in order
    participants: Optional[tuple[str, ...]] = None  # players who took part (starters + subs used)
    extra_time: bool = False

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

    def counts(self, metric: str, period: str) -> Optional[tuple[int, int]]:
        """(home, away) for a metric in a period, or None if unknown."""
        if metric in ('', 'goals'):
            return self.for_period(period)
        if period != 'ft' or self.extra_time:
            return None  # full-match stats only, and they'd include extra time
        return {'corners': self.corners, 'cards': self.cards}.get(metric)

    @property
    def goal_events(self) -> Optional[tuple[GoalEvent, ...]]:
        """Goal events, only if they add up to the score (else they can't be trusted)."""
        if self.goals is None:
            return None
        home = sum(1 for g in self.goals if g.side == 'home')
        away = sum(1 for g in self.goals if g.side == 'away')
        return self.goals if (home, away) == (self.home, self.away) else None


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


def _exact(key: str, n: int) -> Optional[str]:
    try:
        if key.endswith('+'):
            return WON if n >= int(key[:-1]) else LOST
        return WON if n == int(key) else LOST
    except ValueError:
        return None


# -- player names --------------------------------------------------------------

def _name_tokens(name: str) -> list[str]:
    text = unicodedata.normalize('NFKD', name).encode('ascii', 'ignore').decode().lower()
    return [t for t in re.split(r'[^a-z]+', text) if t]


def same_player(a: str, b: str) -> bool:
    """Bookmakers and the stats feed spell names differently ("Bruno Fernandes" vs
    "B. Fernandes"): match on surname plus first initial when both have one."""
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    if ta[-1] != tb[-1]:
        return False
    if len(ta) == 1 or len(tb) == 1:
        return True
    return ta[0][0] == tb[0][0]


def _player_status(label: str, score: Score) -> Optional[str]:
    """'played' | 'absent' | None (unknown / ambiguous) for a named player."""
    if score.participants is None:
        return None
    hits = [p for p in score.participants if same_player(label, p)]
    if len(hits) > 1 and len({tuple(_name_tokens(h)) for h in hits}) > 1:
        return None  # two different players match — don't guess
    return 'played' if hits else 'absent'


def _settle_scorer(kind: str, key: str, label: str, score: Score) -> Optional[str]:
    goals = score.goal_events
    if goals is None:
        return None
    scorers = [g for g in goals if not g.own_goal]
    if key == 'none':  # "No goalscorer"
        return WON if not scorers else LOST
    if kind == 'anytime_scorer':
        candidates = scorers
    elif kind == 'first_scorer':
        candidates = scorers[:1]
    else:
        candidates = scorers[-1:]
    if any(same_player(label, g.player) for g in candidates):
        return WON
    status = _player_status(label, score)
    if status == 'played':
        return LOST
    if status == 'absent':
        return VOID  # didn't take part: stake returned
    return None


# -- entry point ---------------------------------------------------------------

def settle_outcome(
    *, kind: str, period: str, line: Optional[Decimal], key: str, score: Score,
    metric: str = 'goals', label: str = '',
) -> Optional[str]:
    """Settle one outcome. Returns 'won' | 'lost' | 'void', or None if undecidable."""
    period = period or 'ft'

    if kind in ('anytime_scorer', 'first_scorer', 'last_scorer'):
        return _settle_scorer(kind, key, label, score)

    if kind in ('first_team_to_score', 'last_team_to_score'):
        if score.home + score.away == 0:
            return WON if key == 'none' else LOST
        goals = score.goal_events
        if goals is None:
            return None
        side = goals[0].side if kind == 'first_team_to_score' else goals[-1].side
        return WON if key == side else LOST

    if kind == 'own_goal':
        goals = score.goal_events
        return None if goals is None else _yes_no(key, any(g.own_goal for g in goals))

    if kind == 'red_card':
        if score.reds is None or score.extra_time:
            return None
        return _yes_no(key, sum(score.reds) > 0)

    counts = score.counts(metric, period)
    if counts is None:
        return None  # e.g. half-time score or corner count not known
    home, away = counts
    total = Decimal(home + away)

    if kind == 'match_result':
        return WON if key == _result(home, away) else LOST

    if kind == 'double_chance':
        covers = {'1x': ('home', 'draw'), '12': ('home', 'away'), 'x2': ('draw', 'away')}.get(key)
        return None if covers is None else (WON if _result(home, away) in covers else LOST)

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
        return WON if key == _result(int(Decimal(home) + line), away) else LOST

    if kind == 'odd_even':
        if key not in ('odd', 'even'):
            return None
        return WON if (int(total) % 2 == 1) == (key == 'odd') else LOST

    if kind == 'exact_goals':
        return _exact(key, int(total))
    if kind == 'home_exact_goals':
        return _exact(key, home)
    if kind == 'away_exact_goals':
        return _exact(key, away)

    if kind == 'correct_score':
        try:
            want_home, want_away = (int(p) for p in key.split(':'))
        except ValueError:
            return None
        return WON if (home, away) == (want_home, want_away) else LOST

    if kind == 'btts':
        return _yes_no(key, home > 0 and away > 0)
    if kind == 'team_to_score_home':
        return _yes_no(key, home > 0)
    if kind == 'team_to_score_away':
        return _yes_no(key, away > 0)
    if kind == 'clean_sheet_home':
        return _yes_no(key, away == 0)
    if kind == 'clean_sheet_away':
        return _yes_no(key, home == 0)
    if kind == 'win_to_nil_home':
        return _yes_no(key, home > away and away == 0)
    if kind == 'win_to_nil_away':
        return _yes_no(key, away > home and home == 0)
    if kind == 'win_to_nil':
        if key == 'home':
            return WON if home > away and away == 0 else LOST
        if key == 'away':
            return WON if away > home and home == 0 else LOST
        return None

    if kind == 'result_btts':
        try:
            res, btts = key.split('/')
        except ValueError:
            return None
        return WON if res == _result(home, away) and (btts == 'yes') == (home > 0 and away > 0) else LOST

    if kind == 'result_total':
        try:
            res, side = key.split('/')
        except ValueError:
            return None
        total_result = _over_under(side, total, line)
        if total_result is None:
            return None
        if res != _result(home, away):
            return LOST
        return total_result  # includes VOID on a whole line landing exactly

    # -- markets needing the half-time split ------------------------------------
    first, second = score.for_period('1h'), score.for_period('2h')
    if kind in ('ht_ft', 'highest_scoring_half', 'win_both_halves', 'win_either_half', 'score_both_halves'):
        if first is None or second is None:
            return None
        if kind == 'ht_ft':
            return WON if key == f'{_result(*first)}/{_result(home, away)}' else LOST
        if kind == 'highest_scoring_half':
            a, b = sum(first), sum(second)
            actual = '1h' if a > b else '2h' if b > a else 'draw'
            return WON if key == actual else LOST
        if key not in ('home', 'away'):
            return None
        halves = [_result(*first), _result(*second)]
        if kind == 'win_both_halves':
            return WON if halves == [key, key] else LOST
        if kind == 'win_either_half':
            return WON if key in halves else LOST
        idx = 0 if key == 'home' else 1
        return WON if first[idx] > 0 and second[idx] > 0 else LOST

    return None  # manual / unknown kinds are settled by an operator
