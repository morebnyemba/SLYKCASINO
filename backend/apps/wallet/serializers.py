"""wallet transport (DRF)."""
from __future__ import annotations

from rest_framework import serializers

import re

from .models import LedgerEntry, PaymentMethod


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = ['id', 'amount', 'kind', 'reference', 'idempotency_key', 'created_at']


class AdminLedgerEntrySerializer(serializers.ModelSerializer):
    player_id = serializers.IntegerField(source='wallet.player_id', read_only=True)

    class Meta:
        model = LedgerEntry
        fields = ['id', 'player_id', 'amount', 'kind', 'reference', 'idempotency_key', 'created_at']


PUBLIC_METHOD_FIELDS = [
    'code', 'name', 'description', 'speed', 'logo_text', 'color', 'field', 'min_deposit', 'max_deposit',
]


class PaymentMethodSerializer(serializers.ModelSerializer):
    """A deposit option as the player site shows it."""

    class Meta:
        model = PaymentMethod
        fields = PUBLIC_METHOD_FIELDS


class AdminPaymentMethodSerializer(serializers.ModelSerializer):
    """Admin console: every setting, plus whether the live gateway can take it."""
    gateway_supported = serializers.SerializerMethodField()

    class Meta:
        model = PaymentMethod
        fields = ['id', *PUBLIC_METHOD_FIELDS, 'deposit_enabled', 'show_in_footer', 'sort_order',
                  'gateway_supported', 'updated_at']
        read_only_fields = ['id', 'gateway_supported', 'updated_at']

    def get_gateway_supported(self, obj) -> bool:
        from .payments import gateway_supports
        return gateway_supports(obj.code)

    def validate_color(self, value: str) -> str:
        if not re.fullmatch(r'#[0-9a-fA-F]{6}', value or ''):
            raise serializers.ValidationError('Use a hex colour like #e2231a.')
        return value.lower()

    def validate(self, attrs):
        low = attrs.get('min_deposit', getattr(self.instance, 'min_deposit', None))
        high = attrs.get('max_deposit', getattr(self.instance, 'max_deposit', None))
        if low is not None and low <= 0:
            raise serializers.ValidationError({'min_deposit': 'Must be more than 0.'})
        if low is not None and high is not None and high < low:
            raise serializers.ValidationError({'max_deposit': 'Must be at least the minimum.'})
        return attrs
