"""accounts transport (DRF). Read shapes only; mutations go through services."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from apps.wallet import services as wallet_services

from . import utils
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
    """Field-level errors so the signup form can show each one under its input."""
    username = serializers.CharField(max_length=30)
    email = serializers.EmailField(max_length=254)
    password = serializers.CharField(min_length=8, max_length=128, write_only=True, trim_whitespace=False)
    # Wallets are single-currency (USD) for now; anything else is rejected.
    currency = serializers.ChoiceField(choices=['USD'], default='USD')
    # The 18+ / terms attestation: required and must be true (it does not verify age).
    accept_terms = serializers.BooleanField(required=True)

    def validate_username(self, value: str) -> str:
        normalized = utils.normalize_username(value)
        if len(normalized) < 3:
            raise serializers.ValidationError('Use at least 3 letters, numbers or underscores.')
        return value

    def validate_email(self, value: str) -> str:
        return value.strip().lower()

    def validate_accept_terms(self, value: bool) -> bool:
        if value is not True:
            raise serializers.ValidationError('You must confirm you are 18 or older and accept the terms.')
        return value

    def validate(self, attrs):
        user_model = get_user_model()
        username = utils.normalize_username(attrs['username'])
        # One message for either clash, so signup can't be used to probe which
        # usernames or emails have accounts.
        if (
            user_model.objects.filter(username__iexact=username).exists()
            or user_model.objects.filter(email__iexact=attrs['email']).exists()
        ):
            raise serializers.ValidationError('An account with this username or email already exists.')
        candidate = user_model(username=username, email=attrs['email'])
        try:
            validate_password(attrs['password'], user=candidate)
        except DjangoValidationError as exc:
            raise serializers.ValidationError({'password': list(exc.messages)})
        return attrs


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
