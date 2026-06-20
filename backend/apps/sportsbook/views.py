"""sportsbook transport — views move data; placement logic lives in services."""
from __future__ import annotations

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from apps.accounts import services as accounts_services
from apps.wallet.services import InsufficientFunds

from . import services
from .dtos import AccumulatorRequestDTO, BetRequestDTO
from .models import Bet, BetSlip, Event
from .serializers import BetSerializer, BetSlipSerializer, EventSerializer


class EventViewSet(viewsets.ModelViewSet):
    serializer_class = EventSerializer
    # Events are publicly browsable; mutations require auth.
    permission_classes = [AllowAny]

    def get_queryset(self):
        featured = self.request.query_params.get('featured') == 'true'
        sport = self.request.query_params.get('sport')
        return services.list_events(featured=featured or None, sport=sport)

    def get_permissions(self):
        if self.action in ('create', 'update', 'partial_update', 'destroy', 'settle'):
            return [IsAdminUser()]
        return [AllowAny()]

    @action(detail=True, methods=['post'], url_path='settle')
    def settle(self, request, pk=None):
        """Settle every open bet on this event from one result.
        Takes {result: 'home'|'draw'|'away'|'void'}."""
        result = request.data.get('result', '')
        try:
            count = services.settle_event(int(pk), result)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        from apps.accounts.services import audit
        audit(None, 'event_settled', request, event_id=int(pk), result=result, bets_settled=count)
        return Response({'event': int(pk), 'result': result, 'bets_settled': count})


class BetViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = BetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        player = accounts_services.get_current_player(self.request)
        if player is None:
            return Bet.objects.none()
        return Bet.objects.filter(player_id=player.id).order_by('-placed_at')

    def create(self, request, *args, **kwargs):
        player = accounts_services.get_current_player(request)
        if player:
            try:
                accounts_services.check_responsible_gambling(player)
            except ValueError as exc:
                return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        try:
            dto = BetRequestDTO(
                player_id=player.id if player else None,
                event=request.data.get('event'),
                event_id=request.data.get('event_id'),
                selection=request.data.get('selection') or 'home',
                stake=request.data.get('stake'),
                odds=request.data.get('odds'),
            )
            bet = services.place_bet(
                event=dto.event, stake=dto.stake, odds=dto.odds, player_id=dto.player_id,
                event_id=dto.event_id, selection=dto.selection,
            )
        except InsufficientFunds as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_402_PAYMENT_REQUIRED)
        except (ValueError, Exception) as exc:  # noqa: BLE001
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(bet).data, status=status.HTTP_201_CREATED)


class BetSlipViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Accumulator slips for the authenticated player."""
    serializer_class = BetSlipSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        player = accounts_services.get_current_player(self.request)
        if player is None:
            return BetSlip.objects.none()
        return BetSlip.objects.filter(player_id=player.id).prefetch_related('legs').order_by('-placed_at')

    def create(self, request, *args, **kwargs):
        player = accounts_services.get_current_player(request)
        if player:
            try:
                accounts_services.check_responsible_gambling(player)
            except ValueError as exc:
                return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        try:
            dto = AccumulatorRequestDTO(
                player_id=player.id if player else None,
                stake=request.data.get('stake'),
                legs=request.data.get('legs') or [],
            )
            slip = services.place_accumulator(
                stake=dto.stake,
                legs=[leg.model_dump() for leg in dto.legs],
                player_id=dto.player_id,
            )
        except InsufficientFunds as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_402_PAYMENT_REQUIRED)
        except (ValueError, Exception) as exc:  # noqa: BLE001
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(slip).data, status=status.HTTP_201_CREATED)


class AdminBetViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Staff-only view of all bets across all players."""
    serializer_class = BetSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = Bet.objects.order_by('-placed_at')
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs[:200]

    @action(detail=True, methods=['post'], url_path='settle')
    def settle(self, request, pk=None):
        """Settle a bet. Takes {outcome: 'won'|'lost'|'void'}."""
        outcome = request.data.get('outcome', '')
        if outcome not in ('won', 'lost', 'void'):
            return Response(
                {'detail': "outcome must be 'won', 'lost', or 'void'"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            bet = services.settle_bet(int(pk), outcome)
        except Bet.DoesNotExist:
            return Response({'detail': 'Bet not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:  # noqa: BLE001
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        # Audit
        from apps.accounts.services import audit
        audit(bet.player_id, 'bet_settled', request, bet_id=bet.id, outcome=outcome)
        return Response(self.get_serializer(bet).data)
