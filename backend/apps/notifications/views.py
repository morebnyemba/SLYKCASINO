"""notifications transport — read/mark endpoints."""
from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as account_services

from . import services
from .models import Notification
from .serializers import NotificationSerializer


def _player_id(request) -> int | None:
    player = account_services.get_current_player(request)
    return player.id if player else None


class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        player_id = _player_id(request)
        if player_id is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)
        qs = (
            Notification.objects
            .filter(player_id=player_id)
            .order_by('read', '-created_at')[:50]
        )
        return Response(NotificationSerializer(qs, many=True).data)


class NotificationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk: int):
        player_id = _player_id(request)
        if player_id is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)
        found = services.mark_read(player_id, pk)
        if not found:
            return Response({'detail': 'not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({'detail': 'marked read'})


class NotificationReadAllView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        player_id = _player_id(request)
        if player_id is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)
        count = services.mark_all_read(player_id)
        return Response({'detail': f'{count} notifications marked read'})
