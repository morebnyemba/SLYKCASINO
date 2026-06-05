"""promotions transport (DRF)."""
from __future__ import annotations

from rest_framework import serializers

from .models import Promotion


class PromotionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Promotion
        fields = ['id', 'name', 'kind', 'active', 'bonus_amount', 'wagering_multiplier', 'starts_at', 'ends_at']
