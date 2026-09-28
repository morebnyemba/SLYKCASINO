"""sportsbook transport (DRF). Mutations are delegated to services."""
from __future__ import annotations

from rest_framework import serializers

from .models import Bet, BetLeg, BetSlip, Event, Market, MarketOutcome, Team


class TeamSerializer(serializers.ModelSerializer):
    class Meta:
        model = Team
        fields = ['id', 'name', 'logo_url']


class MarketOutcomeSerializer(serializers.ModelSerializer):
    class Meta:
        model = MarketOutcome
        fields = ['id', 'key', 'label', 'odds', 'previous_odds', 'is_open', 'result']


class MarketSerializer(serializers.ModelSerializer):
    outcomes = MarketOutcomeSerializer(many=True, read_only=True)

    class Meta:
        model = Market
        fields = ['id', 'key', 'name', 'group', 'kind', 'period', 'line', 'is_open', 'settled', 'outcomes']


class EventSerializer(serializers.ModelSerializer):
    home_team = TeamSerializer(read_only=True)
    away_team = TeamSerializer(read_only=True)
    # Open secondary markets, for the "+N" link in listings (annotated in the view).
    markets_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Event
        fields = [
            'id', 'name', 'sport', 'odds', 'odds_draw', 'odds_away', 'previous_odds',
            'featured', 'is_open', 'starts_at', 'home_team', 'away_team',
            'status', 'elapsed', 'score_home', 'score_away', 'ht_score_home', 'ht_score_away',
            'markets_count',
        ]
        read_only_fields = ['status', 'elapsed', 'score_home', 'score_away', 'ht_score_home', 'ht_score_away']


class EventDetailSerializer(EventSerializer):
    """Single event with every market — backs the all-markets event page."""
    markets = MarketSerializer(many=True, read_only=True)

    class Meta(EventSerializer.Meta):
        fields = EventSerializer.Meta.fields + ['markets']


class _OutcomeLabelsMixin(serializers.Serializer):
    """Market/outcome names for bets on secondary markets (null for 1X2 bets)."""
    market_name = serializers.CharField(source='outcome_ref.market.name', read_only=True, default=None)
    outcome_label = serializers.CharField(source='outcome_ref.label', read_only=True, default=None)


class BetSerializer(_OutcomeLabelsMixin, serializers.ModelSerializer):
    class Meta:
        model = Bet
        fields = [
            'id', 'event', 'selection', 'outcome_ref', 'market_name', 'outcome_label',
            'stake', 'odds', 'status', 'payout', 'placed_at',
        ]
        read_only_fields = ['status', 'payout', 'placed_at', 'outcome_ref']


class BetLegSerializer(_OutcomeLabelsMixin, serializers.ModelSerializer):
    class Meta:
        model = BetLeg
        fields = ['id', 'event', 'selection', 'outcome_ref', 'market_name', 'outcome_label', 'odds', 'result']


class BetSlipSerializer(serializers.ModelSerializer):
    legs = BetLegSerializer(many=True, read_only=True)

    class Meta:
        model = BetSlip
        fields = ['id', 'stake', 'combined_odds', 'status', 'payout', 'placed_at', 'settled_at', 'legs']
        read_only_fields = ['combined_odds', 'status', 'payout', 'placed_at', 'settled_at']
