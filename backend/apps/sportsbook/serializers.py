"""sportsbook transport (DRF). Mutations are delegated to services."""
from __future__ import annotations

from rest_framework import serializers

from .models import Bet, Event


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
