"""sportsbook transport (DRF). Mutations are delegated to services."""
from __future__ import annotations

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


# Markets listings can switch to instead of 1X2 (the market switcher above the
# match list). The view prefetches just these into `quick_market_list`.
QUICK_MARKET_KEYS = ('double_chance:ft', 'over_under:ft:2.5', 'btts:ft')


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
    quick_markets = serializers.SerializerMethodField()

    def get_quick_markets(self, obj) -> dict:
        """{market key: {id, name, open, outcomes: {outcome key: {id, label, odds, open}}}}."""
        markets = getattr(obj, 'quick_market_list', None)
        if not markets:
            return {}
        return {
            m.key: {
                'id': m.id, 'name': m.name, 'open': bool(m.is_open and not m.settled),
                'outcomes': {
                    o.key: {'id': o.id, 'label': o.label, 'odds': str(o.odds), 'open': o.is_open}
                    for o in m.outcomes.all()
                },
            }
            for m in markets
        }

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

    class Meta:
        model = Event
        fields = [
            'id', 'name', 'sport', 'odds', 'odds_draw', 'odds_away', 'previous_odds', 'has_odds',
            'featured', 'is_open', 'starts_at', 'home_team', 'away_team', 'league',
            'status', 'elapsed', 'score_home', 'score_away', 'ht_score_home', 'ht_score_away',
            'markets_count', 'in_play', 'bettable', 'main_open', 'quick_markets',
        ]
        read_only_fields = ['status', 'elapsed', 'score_home', 'score_away', 'ht_score_home', 'ht_score_away']


class EventDetailSerializer(EventSerializer):
    """Single event with every market — backs the all-markets event page."""
    markets = MarketSerializer(many=True, read_only=True)

    class Meta(EventSerializer.Meta):
        fields = EventSerializer.Meta.fields + ['markets', 'match_facts']
        read_only_fields = EventSerializer.Meta.read_only_fields + ['match_facts']


class BetMatchSerializer(serializers.ModelSerializer):
    """The match a bet (or leg) is on, for the bet ticket: kick-off and score."""

    class Meta:
        model = Event
        fields = ['id', 'name', 'sport', 'starts_at', 'status', 'score_home', 'score_away']


class _OutcomeLabelsMixin(serializers.Serializer):
    """Market/outcome names for bets on secondary markets (null for 1X2 bets),
    plus the linked match (null for legacy free-text bets)."""
    market_name = serializers.CharField(source='outcome_ref.market.name', read_only=True, default=None)
    outcome_label = serializers.CharField(source='outcome_ref.label', read_only=True, default=None)
    match = BetMatchSerializer(source='event_ref', read_only=True, default=None)


class BetSerializer(_OutcomeLabelsMixin, serializers.ModelSerializer):
    class Meta:
        model = Bet
        fields = [
            'id', 'event', 'selection', 'outcome_ref', 'market_name', 'outcome_label', 'match',
            'stake', 'odds', 'status', 'payout', 'placed_at',
        ]
        read_only_fields = ['status', 'payout', 'placed_at', 'outcome_ref']


class BetLegSerializer(_OutcomeLabelsMixin, serializers.ModelSerializer):
    class Meta:
        model = BetLeg
        fields = ['id', 'event', 'selection', 'outcome_ref', 'market_name', 'outcome_label', 'match', 'odds', 'result']


class BetSlipSerializer(serializers.ModelSerializer):
    legs = BetLegSerializer(many=True, read_only=True)

    class Meta:
        model = BetSlip
        fields = [
            'id', 'stake', 'combined_odds', 'status', 'payout', 'bonus_percent', 'bonus',
            'placed_at', 'settled_at', 'legs',
        ]
        read_only_fields = ['combined_odds', 'status', 'payout', 'bonus_percent', 'bonus', 'placed_at', 'settled_at']
