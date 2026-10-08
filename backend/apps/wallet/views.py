"""wallet transport — balance, ledger history, deposit, and withdrawal."""
from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as accounts_services

from . import paynow, payments
from . import psp as psp_registry
from . import services
from .models import LedgerEntry, PaymentMethod, PaymentTransaction
from .serializers import (
    AdminLedgerEntrySerializer, AdminPaymentMethodSerializer, LedgerEntrySerializer, PaymentMethodSerializer,
)

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
        return Response({
            'balance': str(dto.balance), 'currency': dto.currency,
            'deposit_methods': payments.deposit_methods(),
            'payment_methods': PaymentMethodSerializer(payments.offered_methods(), many=True).data,
            'deposit_gateway': 'paynow' if payments.gateway_enabled() else 'stub',
        })


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

        try:
            payments.check_deposit(str(request.data.get('method', '') or ''), amount)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        if payments.gateway_enabled():
            return self._start_gateway_deposit(request, player, amount)

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


    def _start_gateway_deposit(self, request, player, amount):
        """Paynow: the money moves on the player's phone (or Paynow's card page),
        so this only starts the payment; the wallet is credited when Paynow
        confirms it (see payments.apply_status)."""
        dto = services.get_balance_dto(player.id)
        try:
            txn = payments.start_deposit(
                player_id=player.id, amount=amount, currency=dto.currency,
                method=str(request.data.get('method', '')), phone=str(request.data.get('phone', '')),
            )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        except paynow.PaynowError as exc:
            return Response({'detail': f'Payment could not be started: {exc}'}, status=status.HTTP_502_BAD_GATEWAY)
        return Response(_payment_payload(txn), status=status.HTTP_202_ACCEPTED)


def _payment_payload(txn: PaymentTransaction, balance=None) -> dict:
    return {
        'reference': txn.reference, 'status': txn.status, 'method': txn.method,
        'amount': str(txn.amount), 'currency': txn.currency,
        'instructions': txn.instructions, 'redirect_url': txn.redirect_url,
        **({'balance': str(balance)} if balance is not None else {}),
    }


class PaymentStatusView(APIView):
    """GET /api/wallet/deposits/<reference>/ — a gateway deposit's status. While
    pending it re-asks Paynow, so the deposit screen can poll this."""

    def get(self, request, reference: str):
        player, err = _get_player_or_404(request)
        if err:
            return err
        txn = PaymentTransaction.objects.filter(reference=reference, player_id=player.id).first()
        if txn is None:
            return Response({'detail': 'not found'}, status=status.HTTP_404_NOT_FOUND)
        txn = payments.refresh(txn)
        balance = services.get_balance_dto(player.id).balance
        return Response(_payment_payload(txn, balance))


class PaynowResultView(APIView):
    """POST /api/wallet/paynow/result/ — Paynow's server-to-server status
    callback. Unauthenticated by design: the message is signed with our
    integration key and rejected unless the hash verifies."""
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = []

    def post(self, request):
        try:
            payments.handle_result(request.body)
        except paynow.PaynowError:
            return Response({'detail': 'invalid message'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'detail': 'ok'})


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


class AdminLedgerViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Staff-only ledger viewer — GET /api/admin/ledger/?player_id=<id>."""
    serializer_class = AdminLedgerEntrySerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = LedgerEntry.objects.select_related('wallet').order_by('-created_at')
        player_id = self.request.query_params.get('player_id')
        if player_id:
            qs = qs.filter(wallet__player_id=player_id)
        return qs[:500]


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


class PaymentMethodsView(APIView):
    """GET /api/wallet/payment-methods/ — public: the deposit options on offer
    and the method names for the site footer."""
    permission_classes = [AllowAny]

    def get(self, request):
        return Response({
            'deposit': PaymentMethodSerializer(payments.offered_methods(), many=True).data,
            'footer': list(PaymentMethod.objects.filter(show_in_footer=True).values_list('name', flat=True)),
        })


class AdminPaymentMethodViewSet(viewsets.ModelViewSet):
    """/api/admin/payment-methods/ — operators add, edit, reorder and switch
    deposit methods on or off."""
    serializer_class = AdminPaymentMethodSerializer
    permission_classes = [IsAdminUser]
    pagination_class = None
    queryset = PaymentMethod.objects.all()

    def list(self, request, *args, **kwargs):
        response = super().list(request, *args, **kwargs)
        response.data = {
            'gateway': 'paynow' if payments.gateway_enabled() else 'stub',
            'gateway_methods': list(paynow.METHODS),
            'results': response.data,
        }
        return response
