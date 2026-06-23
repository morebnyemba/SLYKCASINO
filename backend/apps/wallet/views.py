"""wallet transport — balance, ledger history, deposit, and withdrawal."""
from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as accounts_services

from . import psp as psp_registry
from . import services
from .models import LedgerEntry
from .serializers import LedgerEntrySerializer

# Header each provider signs its webhook payload with. Anything not listed
# here falls back to a generic header name (and will simply fail that PSP's
# own signature check, since no real secret will match).
_SIGNATURE_HEADERS = {
    'stripe': 'HTTP_STRIPE_SIGNATURE',
}


def _get_player_or_404(request):
    player = accounts_services.get_current_player(request)
    if player is None:
        return None, Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)
    return player, None


class WalletView(APIView):
    """GET /api/wallet/ -> current player's balance."""

    def get(self, request):
        player, err = _get_player_or_404(request)
        if err:
            return err
        dto = services.get_balance_dto(player.id)
        return Response({'balance': str(dto.balance), 'currency': dto.currency})


class LedgerView(APIView):
    """GET /api/wallet/ledger/ -> last 50 ledger entries."""

    def get(self, request):
        player, err = _get_player_or_404(request)
        if err:
            return err
        entries = LedgerEntry.objects.filter(wallet__player_id=player.id).order_by('-created_at')[:50]
        return Response(LedgerEntrySerializer(entries, many=True).data)


class DepositView(APIView):
    """POST /api/wallet/deposit/ — credit the player's wallet (stub PSP)."""

    def post(self, request):
        player, err = _get_player_or_404(request)
        if err:
            return err

        # Responsible gambling: block excluded players.
        try:
            accounts_services.check_responsible_gambling(player)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)

        try:
            amount = Decimal(str(request.data.get('amount', '0')))
            if amount <= 0:
                raise ValueError('amount must be positive')
        except (InvalidOperation, ValueError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Enforce daily deposit limit if set.
        if player.deposit_limit_daily is not None and amount > player.deposit_limit_daily:
            return Response(
                {'detail': f'Amount exceeds your daily deposit limit of {player.deposit_limit_daily}'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        idempotency_key = request.data.get('idempotency_key') or f'deposit:req:{uuid.uuid4()}'
        entry = services.credit(
            player_id=player.id,
            amount=amount,
            kind='deposit',
            idempotency_key=idempotency_key,
            reference='psp:stub',
        )
        dto = services.get_balance_dto(player.id)
        return Response({
            'balance': str(dto.balance),
            'currency': dto.currency,
            'entry': LedgerEntrySerializer(entry).data,
        }, status=status.HTTP_201_CREATED)


class PSPWebhookView(APIView):
    """POST /api/wallet/webhook/<provider>/ — PSP deposit confirmation callback.

    Unauthenticated by design: the PSP's own `verify_webhook` performs
    signature verification against the provider's signing secret, so an
    attacker without that secret cannot forge a deposit confirmation.
    Crediting is idempotent on (provider, provider_ref), so a redelivered
    webhook is a guaranteed no-op rather than a double credit.
    """
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request, provider: str):
        try:
            psp = psp_registry.get_psp(provider)
        except ValueError:
            return Response({'detail': 'unknown provider'}, status=status.HTTP_404_NOT_FOUND)

        signature = request.META.get(_SIGNATURE_HEADERS.get(provider, 'HTTP_X_SIGNATURE'), '')
        try:
            result = psp.verify_webhook(request.body, signature)
        except Exception:
            # Signature mismatch, malformed payload, etc. — never trust an
            # unverified webhook body.
            return Response({'detail': 'invalid webhook'}, status=status.HTTP_400_BAD_REQUEST)

        if result.status != 'completed':
            return Response({'detail': 'ignored'}, status=status.HTTP_200_OK)

        if result.player_id is None:
            return Response({'detail': 'missing player reference'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            services.deposit(
                player_id=result.player_id,
                amount=result.amount,
                idempotency_key=f'wallet:deposit:psp:{provider}:{result.provider_ref}',
                reference=f'psp:{provider}:{result.provider_ref}',
            )
        except ObjectDoesNotExist:
            # Unknown player_id in the PSP metadata — don't 500 and trigger
            # provider retry storms for a payload that will never resolve.
            return Response({'detail': 'player wallet not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'detail': 'ok'}, status=status.HTTP_200_OK)


class WithdrawView(APIView):
    """POST /api/wallet/withdraw/ — debit the player's wallet (stub PSP)."""

    def post(self, request):
        player, err = _get_player_or_404(request)
        if err:
            return err

        # AML/KYC: no payout leaves the platform until identity is verified.
        # (Self-exclusion deliberately does NOT block withdrawals — players must
        # always be able to retrieve their own funds.)
        if player.kyc_status != player.Kyc.VERIFIED:
            return Response(
                {'detail': 'Identity verification is required before you can withdraw.'},
                status=status.HTTP_403_FORBIDDEN,
            )

        try:
            amount = Decimal(str(request.data.get('amount', '0')))
            if amount <= 0:
                raise ValueError('amount must be positive')
        except (InvalidOperation, ValueError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        idempotency_key = request.data.get('idempotency_key') or f'withdrawal:req:{uuid.uuid4()}'
        try:
            entry = services.debit(
                player_id=player.id,
                amount=amount,
                kind='withdrawal',
                idempotency_key=idempotency_key,
                reference='psp:stub',
            )
        except services.InsufficientFunds as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_402_PAYMENT_REQUIRED)

        dto = services.get_balance_dto(player.id)
        return Response({
            'balance': str(dto.balance),
            'currency': dto.currency,
            'entry': LedgerEntrySerializer(entry).data,
        }, status=status.HTTP_201_CREATED)
