"""livechat transport — list + post; posting is delegated to services."""
from __future__ import annotations

from rest_framework import mixins, status, viewsets
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as accounts_services
from common.realtime_auth import make_ws_ticket

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
        before = self.request.query_params.get('before')
        before_id = int(before) if before and before.isdigit() else None
        return services.list_messages(channel=channel, before_id=before_id)

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


class RealtimeTicketView(APIView):
    """GET /api/realtime/ticket/?channel=admin:bets — admin-only.

    Mints a short-lived signed ticket the realtime engine requires to join
    any `admin:*` WebSocket channel, so operator-only feeds (live bet/chat
    streams) can't be joined by an arbitrary, unauthenticated client.
    """
    permission_classes = [IsAdminUser]

    def get(self, request):
        channel = request.query_params.get('channel', '')
        if not channel.startswith('admin:'):
            return Response({'detail': 'channel must start with "admin:"'}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'ticket': make_ws_ticket(channel)})
