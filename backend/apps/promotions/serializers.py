"""promotions transport (DRF)."""
from __future__ import annotations

from rest_framework import serializers

from .models import Promotion, PromotionClaim, Tournament, TournamentEntry


class PromotionSerializer(serializers.ModelSerializer):
    claim_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Promotion
        fields = [
            'id', 'name', 'kind', 'active', 'bonus_amount', 'wagering_multiplier',
            'starts_at', 'ends_at', 'code', 'terms_html', 'claim_count',
        ]


class PromotionClaimSerializer(serializers.ModelSerializer):
    promotion_name = serializers.CharField(source='promotion.name', read_only=True)

    class Meta:
        model = PromotionClaim
        fields = [
            'id', 'promotion', 'promotion_name', 'bonus_amount',
            'wagering_required', 'wagering_progress', 'status',
            'bonus_credited', 'created_at', 'completed_at',
        ]
        read_only_fields = fields


class TournamentSerializer(serializers.ModelSerializer):
    is_live = serializers.BooleanField(read_only=True)
    entry_count = serializers.IntegerField(read_only=True, default=0)

    class Meta:
        model = Tournament
        fields = [
            'id', 'name', 'description', 'metric', 'prize_pool', 'currency',
            'active', 'is_live', 'starts_at', 'ends_at', 'entry_count',
        ]
        read_only_fields = fields


class TournamentEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = TournamentEntry
        fields = ['id', 'player_name', 'score', 'updated_at']
        read_only_fields = fields
