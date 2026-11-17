"""Near-win guard: no in-play bets on a pick the match has as good as won.

`outcome_decided` (live_guard) shuts what the score has settled for certain.
This is the step before: a pick that still needs nothing to happen, with too
little time left for it to happen. "Under 2.5" at 1-0 in the 85th minute
hasn't won yet, but it loses only to two more goals in about eight minutes:
roughly a 96% pick. If the feed's price lags the clock, that pick is free money.

How: goals in the time left follow a Poisson model (a typical
LiveTradingSettings.near_win_goals_per_90 goals per 90 minutes, split home/away), which
gives the chance of every final score from the current one. Each possible final
score is run through the real settlement rules (settlement.settle_outcome),
so every goals market is covered by the same code that pays it: totals, team
totals, 1X2, double chance, BTTS, correct score, exact goals, clean sheets and
the combined markets. A pick whose chance of winning is at least
LiveTradingSettings.near_win_percent is refused in play (and greyed out on the
boards).

The clock carries the decision, not the score alone: "under 2.5" at 1-0 in the
10th minute is a fair ~50% pick and stays open. Team strength is ignored on
purpose: late in a match so few goals are expected that it hardly moves a pick
above or below the cut-off, and the model is used only to refuse, never to price.

Markets it can't model (corners, cards, scorers, first/last team to score,
half-time/full-time, second-half markets) return None and are left to the
other guards.
"""
from __future__ import annotations

from functools import lru_cache
from math import exp
from typing import Optional

from .settlement import WON, Score, settle_outcome

# Share of the expected goals scored by the home side.
HOME_SHARE = 0.55
# Stoppage time still to come, in minutes, on top of the regulation clock.
FIRST_HALF_STOPPAGE = 2
SECOND_HALF_STOPPAGE = 4
# Final scores less likely than this are left out of the sum (their mass is
# counted as "not won", which errs towards keeping a pick open).
MIN_CELL = 1e-7
MAX_EXTRA_GOALS = 12


def minutes_left(status: str, elapsed: Optional[int], period: str) -> Optional[float]:
    """Playing time still to come for a market's period, or None when this
    period can't be modelled from here (it's over, or not regulation goals)."""
    e = max(elapsed or 0, 0)
    if period == '1h':
        if status != '1H':
            return None
        return max(45 - e, 0) + FIRST_HALF_STOPPAGE if e < 45 else 1
    if period != 'ft':
        return None
    if status == '1H':
        return max(45 - e, 0) + FIRST_HALF_STOPPAGE + 45 + SECOND_HALF_STOPPAGE
    if status == 'HT':
        return 45 + SECOND_HALF_STOPPAGE
    if status == '2H':
        # In stoppage time itself (90'+), assume about two minutes are left.
        return (90 - e) + SECOND_HALF_STOPPAGE if e < 90 else 2
    return None


def _poisson(lam: float) -> list[float]:
    out, p = [], exp(-lam)
    for k in range(MAX_EXTRA_GOALS + 1):
        out.append(p)
        p *= lam / (k + 1)
    return out


@lru_cache(maxsize=256)
def extra_goals(minutes: float, goals_per_90: float) -> tuple[tuple[int, int, float], ...]:
    """(home goals, away goals, probability) still to come in `minutes`."""
    lam = goals_per_90 * minutes / 90
    ph, pa = _poisson(lam * HOME_SHARE), _poisson(lam * (1 - HOME_SHARE))
    return tuple((h, a, ph[h] * pa[a]) for h in range(len(ph)) for a in range(len(pa)) if ph[h] * pa[a] >= MIN_CELL)


def win_probability(*, status: str, elapsed: Optional[int], score_home: Optional[int], score_away: Optional[int],
                    kind: str, period: str, line, key: str, metric: str = 'goals', label: str = '',
                    goals_per_90: float = 2.7) -> Optional[float]:
    """Chance this pick wins from the current score and clock, or None when it
    can't be modelled. A void (stake back) counts as not winning."""
    if (metric or 'goals') != 'goals' or score_home is None or score_away is None:
        return None
    period = period or 'ft'
    left = minutes_left(status, elapsed, period)
    if left is None:
        return None
    won = 0.0
    for h, a, p in extra_goals(float(left), float(goals_per_90)):
        home, away = score_home + h, score_away + a
        # In the first half the half-time score is the score now plus what's still to come.
        final = Score(home=home, away=away, ht_home=home, ht_away=away) if period == '1h' else Score(home=home, away=away)
        result = settle_outcome(kind=kind, period=period, line=line, key=key, score=final, metric='goals', label=label)
        if result is None:
            return None  # needs facts the model doesn't have (goal order, scorers…)
        if result == WON:
            won += p
    return won


def _settings():
    from .models import LiveTradingSettings
    return LiveTradingSettings.current()


def threshold() -> Optional[float]:
    """The refusal cut-off as a probability (None = the guard is off)."""
    pct = _settings().near_win_percent
    return pct / 100 if pct else None


def outcome_near_won(event, market, outcome) -> bool:
    """Whether an in-play market outcome is as good as won (see module doc)."""
    from .services import IN_PLAY_STATUSES
    cut = threshold()
    if cut is None or event.status not in IN_PLAY_STATUSES:
        return False
    p = win_probability(
        status=event.status, elapsed=event.elapsed, score_home=event.score_home, score_away=event.score_away,
        kind=market.kind, period=market.period or 'ft', line=market.line, key=outcome.key,
        metric=market.metric or 'goals', label=outcome.label, goals_per_90=float(_settings().near_win_goals_per_90),
    )
    return p is not None and p >= cut


def main_near_won(event, selection: str) -> bool:
    """Whether a headline 1X2 pick ('home' | 'draw' | 'away') is as good as won."""
    from .services import IN_PLAY_STATUSES
    cut = threshold()
    if cut is None or event.status not in IN_PLAY_STATUSES:
        return False
    p = win_probability(
        status=event.status, elapsed=event.elapsed, score_home=event.score_home, score_away=event.score_away,
        kind='match_result', period='ft', line=None, key=selection,
        goals_per_90=float(_settings().near_win_goals_per_90),
    )
    return p is not None and p >= cut


def main_blocked(event) -> list[str]:
    """The 1X2 picks the guard refuses right now (for the boards to grey out)."""
    return [s for s in ('home', 'draw', 'away') if main_near_won(event, s)]
