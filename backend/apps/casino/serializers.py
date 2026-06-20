"""casino transport (DRF)."""
from __future__ import annotations

from rest_framework import serializers

from .models import CrashRound, Game, GameRound


class GameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Game
        fields = ['id', 'slug', 'name', 'provider', 'category', 'rtp', 'is_active', 'image_url']


class GameRoundSerializer(serializers.ModelSerializer):
    class Meta:
        model = GameRound
        fields = ['id', 'game', 'stake', 'win', 'status', 'debit_confirmed', 'created_at', 'settled_at']
        read_only_fields = fields


class RecentWinSerializer(serializers.ModelSerializer):
    game_name = serializers.CharField(source='game.name', read_only=True)

    class Meta:
        model = GameRound
        fields = ['id', 'game_name', 'stake', 'win', 'created_at']
        read_only_fields = fields


class CrashRoundSerializer(serializers.ModelSerializer):
    # The crash growth rate is echoed so the client animates the exact curve the
    # server settles against. The secret seed is only revealed once the round is
    # over, so the committed crash point stays verifiable but unguessable in play.
    growth_rate = serializers.SerializerMethodField()
    server_seed = serializers.SerializerMethodField()
    crash_point = serializers.SerializerMethodField()

    class Meta:
        model = CrashRound
        fields = [
            'id', 'stake', 'status', 'cashout_multiplier', 'win', 'nonce',
            'server_seed_hash', 'server_seed', 'crash_point', 'created_at',
            'settled_at', 'growth_rate',
        ]
        read_only_fields = fields

    def get_growth_rate(self, _obj) -> float:
        from .crash_engine import CRASH_GROWTH_RATE
        return CRASH_GROWTH_RATE

    def _settled(self, obj) -> bool:
        return obj.status != CrashRound.Status.RUNNING

    def get_server_seed(self, obj):
        return obj.server_seed if self._settled(obj) else None

    def get_crash_point(self, obj):
        # Hidden while running — revealing it would let a player time the cash-out.
        return str(obj.crash_point) if self._settled(obj) else None


class CrashHistorySerializer(serializers.ModelSerializer):
    """Public, identity-free recent crash multipliers for the live ticker."""

    class Meta:
        model = CrashRound
        fields = ['id', 'crash_point', 'created_at']
        read_only_fields = fields
