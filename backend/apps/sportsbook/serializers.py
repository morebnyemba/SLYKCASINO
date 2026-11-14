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
        fields = ['id', 'name', 'country', 'logo_url', 'flag_url', 'sort_order']


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


def quick_markets(markets) -> dict:
    """The list prices for one match: full-time goals O/U (the line nearest 2.5),
    double chance and both teams to score, each only when every column is priced."""
    out = {}
    for code, (kind, keys) in QUICK_MARKETS.items():
        candidates = [m for m in markets if m.kind == kind]
        if kind == 'over_under':
            candidates = sorted((m for m in candidates if m.line is not None),
                                key=lambda m: (abs(m.line - Decimal('2.5')), m.line))
        for m in candidates:
            by_key = {o.key: o for o in m.outcomes.all()}
            if all(k in by_key for k in keys):
                out[code] = {
                    'market_id': m.id, 'name': m.name,
                    'line': format(m.line.normalize(), 'f') if m.line is not None else None,
                    'outcomes': [{'id': by_key[k].id, 'key': k, 'label': by_key[k].label, 'odds': str(by_key[k].odds),
                                  'is_open': by_key[k].is_open} for k in keys],
                }
                break
    return out


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
    # O/U, double chance and GG/NG prices for the list's market chips (list view only).
    quick_markets = serializers.SerializerMethodField()

    def get_quick_markets(self, obj):
        markets = getattr(obj, 'quick_list', None)
        return None if markets is None else quick_markets(markets)

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

    class Meta:
        model = Event
        fields = [
            'id', 'name', 'sport', 'odds', 'odds_draw', 'odds_away', 'previous_odds', 'has_odds',
            'featured', 'is_open', 'starts_at', 'home_team', 'away_team', 'league',
            'status', 'elapsed', 'score_home', 'score_away', 'ht_score_home', 'ht_score_away',
            'markets_count', 'in_play', 'bettable', 'main_open', 'live_closed', 'quick_markets',
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
            'stake', 'wallet', 'odds', 'status', 'payout', 'placed_at', 'settled_at', *CASHOUT_FIELDS,
        ]
        read_only_fields = ['code', 'wallet', 'status', 'payout', 'placed_at', 'settled_at', 'outcome_ref', *CASHOUT_FIELDS]


class BetLegSerializer(_OutcomeLabelsMixin, serializers.ModelSerializer):
    class Meta:
        model = BetLeg
        fields = ['id', 'event', 'selection', 'outcome_ref', 'market_name', 'outcome_label', 'match', 'odds', 'result']


class BetSlipSerializer(_CashoutMixin, serializers.ModelSerializer):
    legs = BetLegSerializer(many=True, read_only=True)

    class Meta:
        model = BetSlip
        fields = [
            'id', 'code', 'stake', 'wallet', 'combined_odds', 'status', 'payout', 'bonus_percent', 'bonus',
            'placed_at', 'settled_at', 'legs', *CASHOUT_FIELDS,
        ]
        read_only_fields = ['code', 'wallet', 'combined_odds', 'status', 'payout', 'bonus_percent', 'bonus', 'placed_at', 'settled_at',
                            *CASHOUT_FIELDS]
