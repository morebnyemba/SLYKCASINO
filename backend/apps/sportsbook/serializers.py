"""sportsbook transport (DRF). Mutations are delegated to services."""
from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from .models import Bet, BetLeg, BetSlip, Event, LeagueSetting, Market, MarketOutcome, Team


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ['id', 'name', 'logo_url']


class LeagueSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeagueSetting
        fields = ['id', 'name', 'country', 'logo_url', 'flag_url', 'sort_order', 'top_events']


class MarketOutcomeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketOutcome
        fields = ['id', 'key', 'label', 'odds', 'previous_odds', 'is_open', 'result']


class MarketSerializer(serializers.ModelSerializer):
    outcomes = MarketOutcomeSerializer(many=True, read_only=True)

    class Meta:
        model = Market
        fields = [
            'id', 'key', 'name', 'group', 'kind', 'metric', 'period', 'line', 'is_open', 'settled',
            'needs_review', 'outcomes',
        ]


# Markets a match list can show instead of 1X2 (the chip row above the list):
# code -> (market kind, outcome keys in column order).
QUICK_MARKETS = {
    'ou': ('over_under', ('over', 'under')),
    'dc': ('double_chance', ('1x', '12', 'x2')),
    'gg': ('btts', ('yes', 'no')),
}
QUICK_KINDS = [kind for kind, _ in QUICK_MARKETS.values()]


def quick_markets_for(event_ids) -> dict[int, dict]:
    """The list prices for many matches at once: full-time goals O/U (the line
    nearest 2.5), double chance and both teams to score, each only when every
    column is priced. Two flat queries of plain values — the ORM prefetch this
    replaced built ~27,000 model objects for a 500-match page.

    Compact, as it's embedded once per match in the sportsbook page:
    {code: {"market_id", "line", "outcomes": [{"id", "odds"} | None, ...]}}, outcomes
    in the column order of QUICK_MARKETS (None = that outcome is closed). Labels
    and names are derived by the client from the code and line."""
    from .models import Market, MarketOutcome
    ids = list(event_ids)
    if not ids:
        return {}
    markets = list(Market.objects.filter(
        event_id__in=ids, is_open=True, settled=False, period=Market.Period.FULL_TIME,
        metric=Market.Metric.GOALS, kind__in=QUICK_KINDS,
    ).values('id', 'event_id', 'kind', 'line'))
    outcomes: dict[int, dict[str, tuple]] = {}
    for o in MarketOutcome.objects.filter(market_id__in=[m['id'] for m in markets]).values(
            'id', 'market_id', 'key', 'odds', 'is_open'):
        outcomes.setdefault(o['market_id'], {})[o['key']] = (o['id'], o['odds'], o['is_open'])
    by_event: dict[int, list] = {}
    for m in markets:
        by_event.setdefault(m['event_id'], []).append(m)
    result: dict[int, dict] = {}
    for event_id, ms in by_event.items():
        out = {}
        for code, (kind, keys) in QUICK_MARKETS.items():
            candidates = [m for m in ms if m['kind'] == kind]
            if kind == 'over_under':
                candidates = sorted((m for m in candidates if m['line'] is not None),
                                    key=lambda m: (abs(m['line'] - Decimal('2.5')), m['line']))
            else:
                candidates.sort(key=lambda m: m['id'])
            for m in candidates:
                by_key = outcomes.get(m['id'], {})
                if all(k in by_key for k in keys):
                    out[code] = {
                        'market_id': m['id'],
                        'line': format(m['line'].normalize(), 'f') if m['line'] is not None else None,
                        'outcomes': [{'id': by_key[k][0], 'odds': str(by_key[k][1])} if by_key[k][2] else None
                                     for k in keys],
                    }
                    break
        result[event_id] = out
    return result


class EventSerializer(serializers.ModelSerializer):
    home_team = TeamSerializer(read_only=True)
    away_team = TeamSerializer(read_only=True)
    league = LeagueSerializer(read_only=True)
    # Open secondary markets, for the "+N" link in listings (annotated in the view).
    markets_count = serializers.IntegerField(read_only=True, default=0)
    # Trading state (see services.trading_state): whether the match is trading in
    # play, takes bets at all, and whether its 1X2 is open.
    in_play = serializers.SerializerMethodField()
    bettable = serializers.SerializerMethodField()
    main_open = serializers.SerializerMethodField()
    live_closed = serializers.SerializerMethodField()
    # 1X2 picks the near-win guard refuses right now (greyed out).
    main_blocked = serializers.SerializerMethodField()
    # O/U, double chance and GG/NG prices for the list's market chips (list view only).
    quick_markets = serializers.SerializerMethodField()

    def get_quick_markets(self, obj):
        quick = self.context.get('quick_markets')
        return None if quick is None else quick.get(obj.pk, {})

    def _state(self, obj):
        from .services import trading_state
        cache = self.context.setdefault('_trading_state', {})
        if obj.pk not in cache:
            cache[obj.pk] = trading_state(obj)
        return cache[obj.pk]

    def get_in_play(self, obj) -> bool:
        return self._state(obj)['in_play']

    def get_bettable(self, obj) -> bool:
        return self._state(obj)['bettable']

    def get_main_open(self, obj) -> bool:
        return self._state(obj)['main_open']

    def get_live_closed(self, obj):
        return self._state(obj)['live_closed']

    def get_main_blocked(self, obj) -> list:
        return self._state(obj)['main_blocked']

    class Meta:
        model = Event
        fields = [
            'id', 'name', 'sport', 'odds', 'odds_draw', 'odds_away', 'previous_odds', 'has_odds',
            'featured', 'is_open', 'starts_at', 'home_team', 'away_team', 'league',
            'status', 'elapsed', 'score_home', 'score_away', 'ht_score_home', 'ht_score_away',
            'markets_count', 'in_play', 'bettable', 'main_open', 'live_closed', 'main_blocked', 'quick_markets',
        ]
        read_only_fields = ['status', 'elapsed', 'score_home', 'score_away', 'ht_score_home', 'ht_score_away']


class EventDetailSerializer(EventSerializer):
    """Single event with every market — backs the all-markets event page."""
    markets = MarketSerializer(many=True, read_only=True)

    class Meta(EventSerializer.Meta):
        fields = EventSerializer.Meta.fields + ['markets', 'match_facts']
        read_only_fields = EventSerializer.Meta.read_only_fields + ['match_facts']


class BetMatchSerializer(serializers.ModelSerializer):
    """The match a bet (or leg) is on, for the bet ticket: league, teams,
    kick-off, live clock and half-time / full-time score."""
    home = serializers.CharField(source='home_team.name', read_only=True, default=None)
    away = serializers.CharField(source='away_team.name', read_only=True, default=None)
    league = serializers.SerializerMethodField()

    def get_league(self, obj) -> str | None:
        """'Country - League', as printed on a ticket (e.g. 'England - Premier League')."""
        lg = obj.league
        if lg is None:
            return None
        return f'{lg.country} - {lg.name}' if lg.country else lg.name

    class Meta:
        model = Event
        fields = ['id', 'name', 'sport', 'starts_at', 'status', 'elapsed', 'score_home', 'score_away',
                  'ht_score_home', 'ht_score_away', 'home', 'away', 'league']


class _OutcomeLabelsMixin(serializers.Serializer):
    """Market/outcome names for bets on secondary markets (null for 1X2 bets),
    plus the linked match (null for legacy free-text bets)."""
    market_name = serializers.CharField(source='outcome_ref.market.name', read_only=True, default=None)
    outcome_label = serializers.CharField(source='outcome_ref.label', read_only=True, default=None)
    match = BetMatchSerializer(source='event_ref', read_only=True, default=None)


class _CashoutMixin(serializers.Serializer):
    """The live cash-out offer on an open ticket (null once it's settled)."""
    cashout = serializers.SerializerMethodField()

    def _cashout_settings(self):
        from .models import CashoutSettings
        cache = self.context.setdefault('_cashout_settings', [])
        if not cache:
            cache.append(CashoutSettings.load())
        return cache[0]

    def get_cashout(self, obj):
        # Staff listings skip pricing a live offer for every open ticket.
        if obj.status != 'open' or not obj.player_id or self.context.get('skip_cashout'):
            return None
        from . import cashout
        offer = (cashout.bet_offer if isinstance(obj, Bet) else cashout.slip_offer)(obj, self._cashout_settings())
        return offer.as_dict()


CASHOUT_FIELDS = ['cashout', 'cashout_paid', 'stake_cashed_out', 'cashed_out_at']


class BetSerializer(_CashoutMixin, _OutcomeLabelsMixin, serializers.ModelSerializer):
    class Meta:
        model = Bet
        fields = [
            'id', 'code', 'event', 'selection', 'outcome_ref', 'market_name', 'outcome_label', 'match',
            'stake', 'wallet', 'odds', 'status', 'payout', 'placed_at', 'settled_at', 'in_play', *CASHOUT_FIELDS,
        ]
        read_only_fields = ['code', 'wallet', 'status', 'payout', 'placed_at', 'settled_at', 'outcome_ref', 'in_play',
                            *CASHOUT_FIELDS]


class BetLegSerializer(_OutcomeLabelsMixin, serializers.ModelSerializer):
    class Meta:
        model = BetLeg
        fields = ['id', 'event', 'selection', 'outcome_ref', 'market_name', 'outcome_label', 'match', 'odds', 'result', 'in_play']
        read_only_fields = ['in_play']


class BetSlipSerializer(_CashoutMixin, serializers.ModelSerializer):
    legs = BetLegSerializer(many=True, read_only=True)

    class Meta:
        model = BetSlip
        fields = [
            'id', 'code', 'stake', 'wallet', 'combined_odds', 'status', 'payout', 'bonus_percent', 'bonus',
            'placed_at', 'settled_at', 'legs', 'in_play', *CASHOUT_FIELDS,
        ]
        read_only_fields = ['code', 'wallet', 'combined_odds', 'status', 'payout', 'bonus_percent', 'bonus', 'placed_at', 'settled_at',
                            'in_play', *CASHOUT_FIELDS]
