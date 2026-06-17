"""livechat transport — list + post; posting is delegated to services."""
from __future__ import annotations

from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.accounts import services as accounts_services

from . import services
from .models import ChatMessage
from .serializers import ChatMessageSerializer


class ChatMessageViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = ChatMessageSerializer

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated()]
        return [AllowAny()]

    def get_queryset(self):
        channel = self.request.query_params.get('channel', 'lobby')
        return services.list_messages(channel=channel)

    def create(self, request, *args, **kwargs):
        player = accounts_services.get_current_player(request)
        try:
            message = services.post_message(
                body=request.data.get('body', ''),
                channel=request.data.get('channel', 'lobby'),
                player_id=player.id if player else None,
            )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(message).data, status=status.HTTP_201_CREATED)
