"""sportsbook transport — views move data; placement logic lives in services."""
from __future__ import annotations

from rest_framework import mixins, status, viewsets
from rest_framework.response import Response

from apps.accounts import services as accounts_services
from apps.wallet.services import InsufficientFunds

from . import services
from .dtos import BetRequestDTO
from .models import Bet, Event
from .serializers import BetSerializer, EventSerializer


class EventViewSet(viewsets.ModelViewSet):
    serializer_class = EventSerializer

    def get_queryset(self):
        featured = self.request.query_params.get('featured') == 'true'
        return services.list_events(featured=featured or None)


class BetViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Bet.objects.all()
    serializer_class = BetSerializer

    def create(self, request, *args, **kwargs):
        player = accounts_services.get_current_player(request)
        try:
            dto = BetRequestDTO(
                player_id=player.id if player else None,
                event=request.data.get('event'),
                stake=request.data.get('stake'),
                odds=request.data.get('odds'),
            )
            bet = services.place_bet(
                event=dto.event, stake=dto.stake, odds=dto.odds, player_id=dto.player_id,
            )
        except InsufficientFunds as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_402_PAYMENT_REQUIRED)
        except (ValueError, Exception) as exc:  # noqa: BLE001
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(bet).data, status=status.HTTP_201_CREATED)
