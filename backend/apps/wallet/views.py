"""wallet transport — balance, ledger history, deposit, and withdrawal."""
from __future__ import annotations

import uuid
from decimal import Decimal, InvalidOperation

from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as accounts_services

from . import services
from .models import LedgerEntry
from .serializers import LedgerEntrySerializer


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
        try:
            amount = Decimal(str(request.data.get('amount', '0')))
            if amount <= 0:
                raise ValueError('amount must be positive')
        except (InvalidOperation, ValueError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

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


class WithdrawView(APIView):
    """POST /api/wallet/withdraw/ — debit the player's wallet (stub PSP)."""

    def post(self, request):
        player, err = _get_player_or_404(request)
        if err:
            return err
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
