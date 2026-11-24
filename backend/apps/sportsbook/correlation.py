"""Correlation-aware prices for several picks from the same match.

Picks from one match aren't independent: "Draw" and "Under 2.5" tend to happen
together, "Home win" and "BTTS" much less so. Multiplying their odds would pay
too much on the first and a flat discount would charge too much on the second.

How: each match gets its own goals model, fitted to its own prices. The margin
is taken out of the 1X2 and the over/under 2.5 odds, then expected goals for
each side are found that reproduce them (Poisson, with half-time splits). Every
full-time / half-time score (the same scenarios same_match uses to refuse picks
that clash) is weighted by that model and run through the real settlement rules
(same_match._wins). So:

    correlation = P(all picks win together) / (P(pick 1) × P(pick 2) × …)
    price       = product of the offered odds ÷ correlation

That keeps the margin already in each leg's price and only corrects for how
much the picks move together. Guard rails: never above the straight product
(the house never pays more for a combination than for the picks apart), never
below the longest single price in it.

Picks the score can't settle (corners, cards, scorers) can't be measured, so
each takes the operator's flat same-match % (WalletRules.same_match_price_percent),
as does a match already in play (the model is pre-match) or one without the
prices to fit a model.
"""
from __future__ import annotations

from decimal import ROUND_DOWN, Decimal
from functools import lru_cache
from math import comb, exp
from typing import Optional

from . import same_match

HT_SHARE = 0.45            # share of goals scored before half-time
CENT = Decimal('0.01')


def _poisson(lam: float, n: int = same_match.MAX_GOALS) -> list[float]:
    p = [exp(-lam)]
    for k in range(1, n + 1):
        p.append(p[-1] * lam / k)
    return p


@lru_cache(maxsize=512)
def weights(lam_home: float, lam_away: float) -> tuple[float, ...]:
    """The chance of each same_match scenario (FT score with HT split), in its order."""
    ph, pa = _poisson(lam_home), _poisson(lam_away)
    out = []
    for h in range(same_match.MAX_GOALS + 1):
        for a in range(same_match.MAX_GOALS + 1):
            for hh in range(h + 1):
                for ha in range(a + 1):
                    split = (comb(h, hh) * HT_SHARE ** hh * (1 - HT_SHARE) ** (h - hh)
                             * comb(a, ha) * HT_SHARE ** ha * (1 - HT_SHARE) ** (a - ha))
                    out.append(ph[h] * pa[a] * split)
    total = sum(out)
    return tuple(w / total for w in out)


def _over(lam: float, line: float) -> float:
    """P(total goals > line) for a Poisson total."""
    p = _poisson(lam, 20)
    return 1 - sum(p[: int(line) + 1])


def _bisect(f, lo: float, hi: float, steps: int = 60) -> float:
    for _ in range(steps):
        mid = (lo + hi) / 2
        if f(mid) > 0:
            hi = mid
        else:
            lo = mid
    return (lo + hi) / 2


def _fair(prices: list[Decimal]) -> Optional[list[float]]:
    try:
        inv = [1 / float(p) for p in prices]
    except (TypeError, ZeroDivisionError):
        return None
    if any(p <= 1 for p in prices):
        return None
    s = sum(inv)
    return [i / s for i in inv]


def fit(event) -> Optional[tuple[float, float]]:
    """Expected goals (home, away) that reproduce the match's own 1X2 and
    over/under prices, margin removed. None without a full 1X2."""
    fair = _fair([event.odds, event.odds_draw, event.odds_away]) if event.odds_draw and event.odds_away else None
    if fair is None:
        return None
    p_home, _, p_away = fair
    total, line, p_over = 2.6, 2.5, None
    from .models import Market
    ou = (Market.objects.filter(event=event, kind='over_under', period='ft', metric='goals', settled=False)
          .exclude(line__isnull=True).prefetch_related('outcomes'))
    for m in sorted(ou, key=lambda m: abs(float(m.line) - 2.5)):
        prices = {o.key: o.odds for o in m.outcomes.all()}
        pair = _fair([prices.get('over'), prices.get('under')]) if prices.get('over') and prices.get('under') else None
        if pair:
            line, p_over = float(m.line), pair[0]
            break
    if p_over is not None:
        total = _bisect(lambda t: _over(t, line) - p_over, 0.2, 7.0)

    def edge(share: float) -> float:          # model (home − away) minus the market's
        w = weights(round(total * share, 4), round(total * (1 - share), 4))
        home = away = 0.0
        i = 0
        for h in range(same_match.MAX_GOALS + 1):
            for a in range(same_match.MAX_GOALS + 1):
                n = (h + 1) * (a + 1)
                chunk = sum(w[i:i + n])
                if h > a:
                    home += chunk
                elif a > h:
                    away += chunk
                i += n
        return (home - away) - (p_home - p_away)
    share = _bisect(edge, 0.03, 0.97)
    return round(total * share, 4), round(total * (1 - share), 4)


def group_price(event, legs: list[tuple['same_match.Pick', Decimal]], percent: Decimal, *, in_play: bool = False) -> Decimal:
    """One price for every pick from one match: `legs` = [(pick, offered odds)]."""
    product = Decimal('1')
    for _, odds in legs:
        product *= Decimal(odds)
    if len(legs) <= 1:
        return product
    flat = Decimal(percent) / Decimal('100')
    modelled = [(p, o) for p, o in legs if same_match._wins(p) is not None]
    others = len(legs) - len(modelled)
    model = fit(event) if (event is not None and not in_play and len(modelled) >= 2) else None
    factor = None
    if model is not None:
        w = weights(*model)
        sets = [same_match._wins(p) for p, _ in modelled]
        probs = [sum(w[i] for i in s) for s in sets]
        both = frozenset.intersection(*sets)
        joint = sum(w[i] for i in both)
        if joint > 0 and all(p > 0 for p in probs):
            independent = 1.0
            for p in probs:
                independent *= p
            factor = Decimal(str(independent / joint))
    if factor is None:                         # no model: the flat % for each extra modelled pick
        factor = flat ** max(len(modelled) - 1, 0)
    factor *= flat ** (others if modelled else max(others - 1, 0))
    price = product * factor
    longest = max(Decimal(o) for _, o in legs)
    return min(max(price, longest), product).quantize(CENT, rounding=ROUND_DOWN)
