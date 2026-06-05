"""casino transport — read-only game catalog (play is driven via services)."""
from __future__ import annotations

from rest_framework import mixins, viewsets

from .models import Game
from .serializers import GameSerializer


class GameViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Game.objects.filter(is_active=True)
    serializer_class = GameSerializer
