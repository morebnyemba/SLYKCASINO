"""accounts transport (DRF). Read shapes only; mutations go through services."""
from __future__ import annotations

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

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


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    currency = serializers.CharField(max_length=3, default='USD')


class CustomTokenObtainPairSerializer(TokenObtainPairSerializer):
    @classmethod
    def get_token(cls, user):
        token = super().get_token(user)
        token['is_staff'] = user.is_staff
        token['is_superuser'] = user.is_superuser
        try:
            token['username'] = user.player.username
        except Exception:
            token['username'] = user.username
        return token
