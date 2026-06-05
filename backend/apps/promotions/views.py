"""promotions transport — catalog read; claiming is driven via services."""
from __future__ import annotations

from rest_framework import mixins, viewsets

from . import services
from .serializers import PromotionSerializer


class PromotionViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    serializer_class = PromotionSerializer

    def get_queryset(self):
        return services.list_promotions()
