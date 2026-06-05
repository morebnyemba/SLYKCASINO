"""accounts transport (DRF). Read shapes only; mutations go through services."""
from __future__ import annotations

from rest_framework import serializers

from apps.wallet import services as wallet_services

from .models import Player


class PlayerSerializer(serializers.ModelSerializer):
    # Balance/currency are owned by the wallet domain — derived, never stored here.
    balance = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()

    class Meta:
        model = Player
        fields = ['id', 'username', 'email', 'kyc_status', 'balance', 'currency', 'created_at']

    def get_balance(self, obj: Player) -> str:
        return str(wallet_services.get_balance(obj.id))

    def get_currency(self, obj: Player) -> str:
        return wallet_services.get_currency(obj.id)
