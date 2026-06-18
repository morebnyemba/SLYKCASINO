"""casino transport (DRF)."""
from __future__ import annotations

from rest_framework import serializers

from .models import Game, GameRound


class GameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Game
        fields = ['id', 'slug', 'name', 'provider', 'rtp', 'is_active', 'image_url']


class GameRoundSerializer(serializers.ModelSerializer):
    class Meta:
        model = GameRound
        fields = ['id', 'game', 'stake', 'win', 'status', 'debit_confirmed', 'created_at', 'settled_at']
        read_only_fields = fields
