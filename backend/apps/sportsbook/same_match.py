"""Two picks from the same match on one multiple: allowed when they are
genuinely different bets, refused when they "complement" each other.

Rather than a hand-kept list of forbidden pairs, every realistic result is
played through the real settlement rules (settlement.settle_outcome): full-time
scores 0-0 to 7-7 with every half-time split. For two picks A and B:

  * never both win             -> contradict  (Home + Away, Over 2.5 + Under 1.5)
  * A winning always means B   -> implies     (Home + Double chance 1X,
                                               Over 2.5 + Over 1.5, 2-1 + Home)
  * otherwise                  -> different   (Home + BTTS, Over 2.5 + Odd goals)

Markets the score can't decide (corners, cards, scorers) can't be proven
related, so they're treated as different. Two picks in the same market are
always refused. Pure functions — callers pass outcome specs, not models.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from functools import lru_cache
from itertools import combinations
from typing import Iterable, Optional

from .settlement import LOST, WON, Score, settle_outcome

MAX_GOALS = 7


@dataclass(frozen=True)
class Pick:
    """What a leg backs, enough to settle it from a score."""
    market: str          # market identity: 'mr' for the headline 1X2, else the market id
    kind: str
    period: str = 'ft'
    line: Optional[Decimal] = None
    metric: str = 'goals'
    key: str = ''
    label: str = ''
    name: str = ''       # shown to the player, e.g. "Total goals 2.5: Over"


@lru_cache(maxsize=1)
def _scenarios() -> tuple[Score, ...]:
    out = []
    for h in range(MAX_GOALS + 1):
        for a in range(MAX_GOALS + 1):
            for hh in range(h + 1):
                for ha in range(a + 1):
                    out.append(Score(home=h, away=a, ht_home=hh, ht_away=ha))
    return tuple(out)


@lru_cache(maxsize=4096)
def _wins(pick: Pick) -> Optional[frozenset[int]]:
    """Indexes of the scenarios where the pick wins, or None when the score
    alone can't settle it (corners, cards, scorers...)."""
    won = set()
    for i, score in enumerate(_scenarios()):
        try:
            r = settle_outcome(kind=pick.kind, period=pick.period, line=pick.line, key=pick.key, score=score,
                               metric=pick.metric, label=pick.label)
        except Exception:  # noqa: BLE001 — an unknown market is simply "can't tell"
            return None
        if r is None:
            return None
        if r == WON:
            won.add(i)
    return frozenset(won)


def relation(a: Pick, b: Pick) -> str:
    """'same_market' | 'contradict' | 'implies' | 'different'."""
    if a.market == b.market:
        return 'same_market'
    wa, wb = _wins(a), _wins(b)
    if wa is None or wb is None or not wa or not wb:
        return 'different'
    if not wa & wb:
        return 'contradict'
    if wa <= wb or wb <= wa:
        return 'implies'
    return 'different'


MESSAGES = {
    'same_market': '{a} and {b} are in the same market — pick one.',
    'contradict': '{a} and {b} can never both win.',
    'implies': '{a} and {b} overlap — one already includes the other, so they can’t go on the same multiple.',
}


def problems(picks: Iterable[Pick]) -> list[tuple[Pick, Pick, str]]:
    """Every pair of picks (from one match) that can't share a multiple, with why."""
    found = []
    for a, b in combinations(list(picks), 2):
        rel = relation(a, b)
        if rel != 'different':
            found.append((a, b, MESSAGES[rel].format(a=a.name or a.key, b=b.name or b.key)))
    return found


def price_factor(legs_in_match: int, percent: Decimal) -> Decimal:
    """Same-match picks are correlated (Home win and Over 2.5 tend to happen
    together), so each extra pick from one match multiplies the price by
    `percent` (100 = straight product)."""
    if legs_in_match <= 1:
        return Decimal('1')
    return (Decimal(percent) / Decimal('100')) ** (legs_in_match - 1)
