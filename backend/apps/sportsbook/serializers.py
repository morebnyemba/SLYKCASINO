"""sportsbook transport (DRF). Mutations are delegated to services."""
from __future__ import annotations

from rest_framework import serializers

from .models import Bet, BetLeg, BetSlip, Event


class EventSerializer(serializers.ModelSerializer):
    class Meta:
        model = Event
        fields = [
            'id', 'name', 'sport', 'odds', 'odds_draw', 'odds_away', 'previous_odds',
            'featured', 'is_open', 'starts_at',
        ]


class BetSerializer(serializers.ModelSerializer):
    class Meta:
        model = Bet
        fields = ['id', 'event', 'selection', 'stake', 'odds', 'status', 'payout', 'placed_at']
        read_only_fields = ['status', 'payout', 'placed_at']


class BetLegSerializer(serializers.ModelSerializer):
    class Meta:
        model = BetLeg
        fields = ['id', 'event', 'selection', 'odds', 'result']


class BetSlipSerializer(serializers.ModelSerializer):
    legs = BetLegSerializer(many=True, read_only=True)

    class Meta:
        model = BetSlip
        fields = ['id', 'stake', 'combined_odds', 'status', 'payout', 'placed_at', 'settled_at', 'legs']
        read_only_fields = ['combined_odds', 'status', 'payout', 'placed_at', 'settled_at']
