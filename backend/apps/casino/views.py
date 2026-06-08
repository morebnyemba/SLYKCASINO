"""casino transport — game catalog, instant play, round history."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts import services as accounts_services
from apps.wallet import services as wallet_services
from apps.wallet.services import InsufficientFunds

from . import services
from .models import Game, GameRound
from .serializers import GameRoundSerializer, GameSerializer


class GameViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Game.objects.filter(is_active=True)
    serializer_class = GameSerializer
    permission_classes = [AllowAny]

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated], url_path='play')
    def play(self, request, pk=None):
        """POST /api/casino/games/{id}/play/ — instant spin: debit, settle, return outcome."""
        player = accounts_services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            stake = Decimal(str(request.data.get('stake', '0')))
            if stake <= 0:
                raise ValueError('stake must be positive')
        except (InvalidOperation, ValueError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Responsible gambling check.
        try:
            accounts_services.check_responsible_gambling(player)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)

        try:
            rnd = services.start_round(player_id=player.id, game_id=int(pk), stake=stake)
        except InsufficientFunds as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_402_PAYMENT_REQUIRED)
        except Exception as exc:  # noqa: BLE001
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Settle immediately using the stub provider outcome.
        from .clients import CasinoProviderClient
        outcome = CasinoProviderClient().settle_round(rnd.provider_round_ref, stake=stake)
        rnd = services.settle_round(rnd.id, win=outcome.win)

        balance_dto = wallet_services.get_balance_dto(player.id)
        return Response({
            'round': GameRoundSerializer(rnd).data,
            'win': str(rnd.win),
            'balance': str(balance_dto.balance),
            'currency': balance_dto.currency,
        }, status=status.HTTP_201_CREATED)


class GameRoundViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = GameRoundSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        player = accounts_services.get_current_player(self.request)
        if player is None:
            return GameRound.objects.none()
        return GameRound.objects.filter(player_id=player.id).order_by('-created_at')[:50]
