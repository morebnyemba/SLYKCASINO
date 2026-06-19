"""promotions transport — catalog read; claiming is driven via services."""
from __future__ import annotations

from django.db.models import Count

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts import services as accounts_services

from . import services
from .models import PromotionClaim, Tournament
from .serializers import (
    PromotionClaimSerializer,
    PromotionSerializer,
    TournamentEntrySerializer,
    TournamentSerializer,
)


class PromotionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PromotionSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return services.list_promotions()

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated], url_path='claim')
    def claim(self, request, pk=None):
        """POST /api/promotions/{id}/claim/ — claim a promotion bonus."""
        player = accounts_services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)
        try:
            claim = services.claim_promotion(player_id=player.id, promotion_id=int(pk))
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PromotionClaimSerializer(claim).data, status=status.HTTP_201_CREATED)


class MyClaimsViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = PromotionClaimSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        player = accounts_services.get_current_player(self.request)
        if player is None:
            return PromotionClaim.objects.none()
        return PromotionClaim.objects.filter(player_id=player.id).order_by('-id')


class TournamentViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = TournamentSerializer
    permission_classes = [AllowAny]

    def get_queryset(self):
        return services.list_tournaments().annotate(entry_count=Count('entries'))

    @action(detail=True, methods=['get'], permission_classes=[AllowAny], url_path='leaderboard')
    def leaderboard(self, request, pk=None):
        """GET /api/promotions/tournaments/{id}/leaderboard/ — top entries (public)."""
        rows = services.leaderboard(int(pk))
        return Response(TournamentEntrySerializer(rows, many=True).data)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated], url_path='join')
    def join(self, request, pk=None):
        """POST /api/promotions/tournaments/{id}/join/ — opt the player in."""
        player = accounts_services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)
        try:
            entry = services.join_tournament(
                player_id=player.id, player_name=player.username, tournament_id=int(pk),
            )
        except Tournament.DoesNotExist:
            return Response({'detail': 'tournament not found'}, status=status.HTTP_404_NOT_FOUND)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(TournamentEntrySerializer(entry).data, status=status.HTTP_201_CREATED)
