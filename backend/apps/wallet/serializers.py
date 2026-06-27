"""wallet transport (DRF)."""
from __future__ import annotations

from rest_framework import serializers

from .models import LedgerEntry


class LedgerEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = LedgerEntry
        fields = ['id', 'amount', 'kind', 'reference', 'idempotency_key', 'created_at']


class AdminLedgerEntrySerializer(serializers.ModelSerializer):
    player_id = serializers.IntegerField(source='wallet.player_id', read_only=True)

    class Meta:
        model = LedgerEntry
        fields = ['id', 'player_id', 'amount', 'kind', 'reference', 'idempotency_key', 'created_at']
