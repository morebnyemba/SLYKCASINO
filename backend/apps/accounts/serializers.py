"""accounts transport (DRF). Read shapes only; mutations go through services."""
from __future__ import annotations

from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.wallet import services as wallet_services

from .models import AuditLog, KYCSubmission, Player


class PlayerSerializer(serializers.ModelSerializer):
    # Balance/currency are owned by the wallet domain — derived, never stored here.
    balance = serializers.SerializerMethodField()
    currency = serializers.SerializerMethodField()

    class Meta:
        model = Player
        fields = [
            'id', 'username', 'email', 'kyc_status', 'balance', 'currency',
            'created_at', 'avatar_url', 'loyalty_tier',
            'is_suspended', 'suspended_reason', 'suspended_at',
        ]

    def get_balance(self, obj: Player) -> str:
        return str(wallet_services.get_balance(obj.id))

    def get_currency(self, obj: Player) -> str:
        return wallet_services.get_currency(obj.id)


class RegisterSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=150)
    email = serializers.EmailField()
    password = serializers.CharField(min_length=8, write_only=True)
    currency = serializers.CharField(max_length=3, default='USD')


class KYCSubmissionSerializer(serializers.ModelSerializer):
    username = serializers.CharField(source='player.username', read_only=True)

    class Meta:
        model = KYCSubmission
        fields = [
            'id', 'player', 'username', 'document_type', 'status',
            'rejection_reason', 'submitted_at', 'reviewed_at', 'reviewed_by_username',
        ]
        read_only_fields = fields


class KYCSubmitSerializer(serializers.Serializer):
    document_type = serializers.ChoiceField(choices=KYCSubmission.DocumentType.choices)
    file = serializers.FileField()


class KYCRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255)


class SuspendPlayerSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=255, allow_blank=True, default='')


class AdjustBalanceSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=12, decimal_places=2)
    reason = serializers.CharField(max_length=255)


class AuditLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditLog
        fields = ['id', 'player_id', 'event_type', 'ip_address', 'metadata', 'created_at']
        read_only_fields = fields


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

    def validate(self, attrs):
        # The login form takes "username or email": resolve an email (or a
        # differently-cased username) to the account's actual username.
        from django.contrib.auth import get_user_model
        User = get_user_model()
        given = (attrs.get(self.username_field) or '').strip()
        if given and not User.objects.filter(**{self.username_field: given}).exists():
            lookup = {'email__iexact': given} if '@' in given else {f'{self.username_field}__iexact': given}
            match = User.objects.filter(**lookup).values_list(self.username_field, flat=True)[:2]
            if len(match) == 1:
                attrs[self.username_field] = match[0]
        data = super().validate(attrs)
        player = getattr(self.user, 'player', None)
        if player is not None and player.is_suspended and not self.user.is_staff:
            raise serializers.ValidationError('This account has been suspended. Contact support.')
        return data
