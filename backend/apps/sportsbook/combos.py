"""Ready-made combined picks for a match ("Home & Over 1.5", "1X & BTTS YES"...), for the
match page's Combined tab and the WhatsApp bot.

Built only from prices the match really has open right now: every pair of playable picks
from two different markets that are genuinely different bets (same_match.relation ==
'different': never two that contradict or where one includes the other), priced the way the
ticket will be (correlation.group_price, one goals model fitted once per match). Tapping one
puts its two legs on the slip; placing re-checks every price and rule as usual, so this
module can't create a price the house wouldn't accept.

A match with the usual markets (1X2, double chance, five over/under lines, both teams to
score, odd/even, team totals, half-time) gives a few hundred pairs; one with only a 1X2 gives
none, because inventing prices for markets the feed doesn't quote would be a hole.
"""
from __future__ import annotations

from decimal import Decimal
from itertools import combinations
from typing import Optional

from django.core.cache import cache

# Markets whose result the score decides (so pairs can be checked and priced) and that read well paired.
KINDS = {'match_result', 'double_chance', 'over_under', 'btts', 'odd_even', 'home_over_under', 'away_over_under',
         'team_to_score_home', 'team_to_score_away', 'clean_sheet_home', 'clean_sheet_away'}
MIN_ODDS = Decimal('1.10')          # pairs paying less than this aren't worth a tap
MAX_ODDS = Decimal('500')
MAX_COMBOS = 300

# Families decide the group a pair is shown under, in this order.
FAMILY_LABEL = {'result': 'Result', 'dc': 'Double chance', 'goals': 'Goals', 'btts': 'Both teams to score',
                'team': 'Team goals', 'oddeven': 'Odd/Even', 'half': '1st half'}
GROUP_ORDER = [('result', 'goals'), ('result', 'btts'), ('dc', 'goals'), ('dc', 'btts'), ('goals', 'btts'),
               ('result', 'team'), ('dc', 'team'), ('btts', 'team'), ('goals', 'team'), ('result', 'half'),
               ('half', 'goals'), ('result', 'oddeven'), ('goals', 'oddeven'), ('btts', 'oddeven')]
FAMILY_RANK = {f: i for i, f in enumerate(FAMILY_LABEL)}


def _family(kind: str, period: str) -> str:
    if period == '1h':
        return 'half'
    return {'match_result': 'result', 'double_chance': 'dc', 'over_under': 'goals', 'btts': 'btts',
            'odd_even': 'oddeven'}.get(kind, 'team')


def _group(a: str, b: str) -> tuple[int, str]:
    x, y = sorted((a, b), key=lambda f: FAMILY_RANK[f])
    label = FAMILY_LABEL[x] + ' & ' + FAMILY_LABEL[y] if x != y else FAMILY_LABEL[x]
    try:
        return GROUP_ORDER.index((x, y)), label
    except ValueError:
        return len(GROUP_ORDER), label


def _picks(event, *, now=None) -> list[dict]:
    """Every playable pick the combos may use, with its settle spec and slip leg."""
    from . import pick_names, services as sb
    from .models import Market
    from .same_match import Pick, _wins
    in_play = sb._started(event)
    event_ok = sb.in_play_bettable(event, now=now) if in_play else event.is_open
    if not event_ok:
        return []
    out = []
    state = sb.trading_state(event, now=now)
    if state['main_open']:
        blocked = set(state.get('main_blocked') or [])
        for sel, price in (('home', event.odds), ('draw', event.odds_draw), ('away', event.odds_away)):
            if price is not None and price > 1 and sel not in blocked:
                out.append({'pick': Pick(market='mr', kind='match_result', key=sel), 'family': 'result',
                            'odds': Decimal(price), 'short': pick_names.name(event=event, selection=sel),
                            'leg': {'event_id': event.pk, 'selection': sel, 'odds': str(price)}})
    markets = (Market.objects.filter(event=event, is_open=True, settled=False, kind__in=KINDS, metric='goals',
                                     period__in=('ft', '1h')).prefetch_related('outcomes'))
    for m in markets:
        if m.kind == 'match_result' and m.period == 'ft':
            continue                                    # the headline 1X2 is the event's own prices above
        for o in m.outcomes.all():
            if sb.outcome_unavailable(event, m, o, in_play=in_play, event_ok=event_ok) is not None:
                continue
            pick = Pick(market=str(m.id), kind=m.kind, period=m.period or 'ft', line=m.line, metric=m.metric,
                        key=o.key, label=o.label)
            if not _wins(pick):
                continue                                # the score can't settle it: can't be checked or priced
            out.append({'pick': pick, 'family': _family(m.kind, m.period), 'odds': Decimal(o.odds),
                        'short': pick_names.name(event=event, market=m, outcome=o),
                        'leg': {'event_id': event.pk, 'outcome_id': o.pk, 'odds': str(o.odds), 'market_id': m.pk,
                                'market_name': m.name, 'outcome_label': o.label}})
    return out


def build(event, *, now=None) -> list[dict]:
    """The match's combined picks, best groups first, cheapest first within a group."""
    from apps.wallet.models import WalletRules

    from . import correlation, services as sb
    from .same_match import relation
    rules = WalletRules.load()
    if not rules.same_match_bets or rules.max_picks_per_match < 2:
        return []
    picks = _picks(event, now=now)
    if len(picks) < 2:
        return []
    in_play = sb._started(event)
    model = None if in_play else correlation.fit(event)
    found = []
    for a, b in combinations(picks, 2):
        if a['pick'].market == b['pick'].market or relation(a['pick'], b['pick']) != 'different':
            continue
        odds = correlation.group_price(event, [(a['pick'], a['odds']), (b['pick'], b['odds'])],
                                       rules.same_match_price_percent, in_play=in_play, model=model)
        if not MIN_ODDS <= odds <= MAX_ODDS:
            continue
        rank, label = _group(a['family'], b['family'])
        first, second = (a, b) if FAMILY_RANK[a['family']] <= FAMILY_RANK[b['family']] else (b, a)
        found.append((rank, odds, {
            'key': '-'.join(str(p['leg'].get('outcome_id') or p['leg']['selection']) for p in (first, second)),
            'group': label, 'name': f'{first["short"]} & {second["short"]}', 'odds': str(odds),
            'legs': [{**first['leg'], 'name': first['short']}, {**second['leg'], 'name': second['short']}],
        }))
    found.sort(key=lambda r: (r[0], r[1]))
    return [r[2] for r in found[:MAX_COMBOS]]


def for_event(event_id: int) -> Optional[dict]:
    """{'event_id', 'count', 'groups': [...], 'combos': [...]} for the API, cached briefly
    (a few seconds in play, where prices move)."""
    from .models import Event
    from . import services as sb
    event = Event.objects.select_related('home_team', 'away_team').filter(pk=event_id).first()
    if event is None:
        return None
    in_play = sb._started(event)
    key = f'sb:combos:{event.pk}:{event.odds}:{event.odds_draw}:{event.odds_away}:{int(in_play)}'
    data = cache.get(key)
    if data is None:
        combos = build(event)
        groups = list(dict.fromkeys(c['group'] for c in combos))
        data = {'event_id': event.pk, 'count': len(combos), 'groups': groups, 'combos': combos}
        cache.set(key, data, 5 if in_play else 30)
    return data
