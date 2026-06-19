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
from .models import CrashRound, Game, GameRound
from .serializers import (
    CrashHistorySerializer,
    CrashRoundSerializer,
    GameRoundSerializer,
    GameSerializer,
    RecentWinSerializer,
)


class GameViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Game.objects.filter(is_active=True)
    serializer_class = GameSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        qs = super().get_queryset()
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)
        return qs

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

    @action(detail=False, methods=['get'], permission_classes=[AllowAny], url_path='recent-wins')
    def recent_wins(self, request):
        """GET /api/casino/rounds/recent-wins/ — public win ticker (no player identity)."""
        qs = GameRound.objects.filter(status='settled', win__gt=0).select_related('game').order_by('-created_at')[:10]
        return Response(RecentWinSerializer(qs, many=True).data)


class CrashViewSet(viewsets.ViewSet):
    """Aviator-style crash game: place a bet, then cash out before the bust."""

    permission_classes = [IsAuthenticated]

    def create(self, request):
        """POST /api/casino/crash/ — place a crash bet (debits the stake)."""
        player = accounts_services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            stake = Decimal(str(request.data.get('stake', '0')))
            if stake <= 0:
                raise ValueError('stake must be positive')
        except (InvalidOperation, ValueError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            accounts_services.check_responsible_gambling(player)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)

        try:
            rnd = services.place_crash_bet(player_id=player.id, stake=stake)
        except InsufficientFunds as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_402_PAYMENT_REQUIRED)
        except Exception as exc:  # noqa: BLE001
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(CrashRoundSerializer(rnd).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='cashout')
    def cashout(self, request, pk=None):
        """POST /api/casino/crash/{id}/cashout/ — cash out (optional `multiplier` target)."""
        player = accounts_services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)

        target = None
        raw_target = request.data.get('multiplier')
        if raw_target is not None:
            try:
                target = Decimal(str(raw_target))
            except InvalidOperation:
                return Response({'detail': 'multiplier is malformed'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            rnd = services.cashout_crash(player_id=player.id, crash_id=int(pk), target=target)
        except CrashRound.DoesNotExist:
            return Response({'detail': 'round not found'}, status=status.HTTP_404_NOT_FOUND)

        balance_dto = wallet_services.get_balance_dto(player.id)
        return Response({
            'round': CrashRoundSerializer(rnd).data,
            'balance': str(balance_dto.balance),
            'currency': balance_dto.currency,
        })

    @action(detail=False, methods=['get'], permission_classes=[AllowAny], url_path='history')
    def history(self, request):
        """GET /api/casino/crash/history/ — recent settled crash multipliers (public)."""
        qs = CrashRound.objects.exclude(status=CrashRound.Status.RUNNING).order_by('-created_at')[:20]
        return Response(CrashHistorySerializer(qs, many=True).data)
