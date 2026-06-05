"""accounts transport — views move data; all logic is in services."""
from __future__ import annotations

from rest_framework import mixins, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from . import services
from .models import Player
from .serializers import PlayerSerializer


class PlayerViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Player.objects.all()
    serializer_class = PlayerSerializer

    @action(detail=False, methods=['get'])
    def me(self, request):
        player = services.get_current_player(request)
        if player is None:
            return Response({'username': None, 'email': None, 'kyc_status': 'unverified'})
        return Response(self.get_serializer(player).data)
