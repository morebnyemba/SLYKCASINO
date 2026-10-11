"""livechat transport — list + post; posting is delegated to services."""
from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as accounts_services
from common.realtime_auth import make_ws_ticket

from . import services


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


class SupportChatView(APIView):
    """GET /api/support/messages/ — the player's own conversation with support
    (marks support's replies read); POST {body} — send a message. Nobody else
    can read it except staff."""
    permission_classes = [IsAuthenticated]

    def _player(self, request):
        return accounts_services.get_current_player(request)

    def get(self, request):
        from . import support
        player = self._player(request)
        if player is None:
            return Response({'detail': 'Player not found.'}, status=status.HTTP_404_NOT_FOUND)
        messages = support.thread(player.id)
        support.mark_read(player.id, by_staff=False)
        return Response({'results': [support.payload(m) for m in messages]})

    def post(self, request):
        from . import support
        player = self._player(request)
        if player is None:
            return Response({'detail': 'Player not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            msg = support.player_post(player_id=player.id, body=request.data.get('body', ''))
        except support.SupportError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(support.payload(msg), status=status.HTTP_201_CREATED)


class AdminSupportInboxView(APIView):
    """GET /api/admin/support/?q= — every player's conversation, newest first, with unread counts."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        from . import support
        return Response({'results': support.inbox(q=(request.query_params.get('q') or '').strip()),
                         'unread_threads': support.unread_threads()})


class AdminSupportThreadView(APIView):
    """GET /api/admin/support/<player_id>/ — one conversation (marks the player's
    messages read); POST {body} — reply as staff (the player is notified)."""
    permission_classes = [IsAdminUser]

    def get(self, request, player_id: int):
        from apps.accounts.models import Player
        from . import support
        player = Player.objects.filter(pk=player_id).first()
        messages = support.thread(player_id)
        support.mark_read(player_id, by_staff=True)
        return Response({
            'player': {'id': player_id, 'username': player.username if player else '(deleted)',
                       'email': player.email if player else '', 'kyc_status': player.kyc_status if player else None},
            'results': [{**support.payload(m), 'sender': (m.staff_name or 'Staff') if m.from_staff else (player.username if player else 'Player')}
                        for m in messages],
        })

    def post(self, request, player_id: int):
        from apps.accounts.models import Player
        from . import support
        if not Player.objects.filter(pk=player_id).exists():
            return Response({'detail': 'Player not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            msg = support.staff_reply(player_id=player_id, body=request.data.get('body', ''),
                                      staff_name=request.user.get_full_name() or request.user.get_username())
        except support.SupportError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(support.payload(msg), status=status.HTTP_201_CREATED)
