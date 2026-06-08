"""promotions transport — catalog read; claiming is driven via services."""
from __future__ import annotations

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts import services as accounts_services

from . import services
from .models import PromotionClaim
from .serializers import PromotionClaimSerializer, PromotionSerializer


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
