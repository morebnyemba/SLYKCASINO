"""Group chat endpoints. Players: /api/chat/…; staff moderation: /api/admin/chat/…"""
from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as accounts_services
from apps.accounts.impersonation import is_impersonated

from . import rooms
from .models import ChatRoom


def _err(exc: rooms.ChatError) -> Response:
    return Response({'detail': str(exc)}, status=exc.code)


def _int(value):
    try:
        return int(value) if value not in (None, '') else None
    except (TypeError, ValueError):
        return None


def _staff_name(request) -> str:
    return request.user.get_full_name() or request.user.get_username()


# -- players --------------------------------------------------------------------

class _PlayerView(APIView):
    permission_classes = [IsAuthenticated]

    def player(self, request):
        player = accounts_services.get_current_player(request)
        if player is None:
            raise rooms.ChatError('Player not found.', 404)
        return player


class RoomsView(_PlayerView):
    """GET /api/chat/rooms/ — the rooms I can read, with unread counts and whether I can post."""

    def get(self, request):
        try:
            player = self.player(request)
        except rooms.ChatError as exc:
            return _err(exc)
        mute = rooms.mute_of(player.id)
        return Response({
            'results': rooms.room_rows(player_id=player.id),
            'me': {'role': rooms.role_of(player.id), 'username': player.username,
                   'muted': mute is not None, 'muted_until': mute.until.isoformat() if mute and mute.until else None},
        })


class RoomMessagesView(_PlayerView):
    """GET /api/chat/rooms/<slug>/messages/?after=&before= — a page of messages
    (marks the room read); POST {body, reply_to?} — send one."""

    def get(self, request, slug: str):
        try:
            player = self.player(request)
            room = rooms.room_for(slug, player_id=player.id)
        except rooms.ChatError as exc:
            return _err(exc)
        after, before = _int(request.query_params.get('after')), _int(request.query_params.get('before'))
        page = rooms.messages(room, after=after, before=before)
        if not is_impersonated(request):
            rooms.mark_read(room, player.id)
        return Response({
            'results': [rooms.message_row(m, me=player.id) for m in page],
            'pinned': [rooms.message_row(m, me=player.id) for m in rooms.pinned(room)] if after is None else None,
            'has_more': after is None and len(page) == rooms.PAGE,
        })

    def post(self, request, slug: str):
        try:
            player = self.player(request)
            room = rooms.room_for(slug, player_id=player.id)
            message = rooms.player_post(player=player, room=room, body=request.data.get('body'),
                                        reply_to=request.data.get('reply_to'))
        except rooms.ChatError as exc:
            return _err(exc)
        return Response(rooms.message_row(message, me=player.id), status=status.HTTP_201_CREATED)


class ReportMessageView(_PlayerView):
    """POST /api/chat/messages/<id>/report/ {reason?} — flag a message for staff."""

    def post(self, request, pk: int):
        try:
            rooms.report(message_id=pk, player_id=self.player(request).id, reason=str(request.data.get('reason') or ''))
        except rooms.ChatError as exc:
            return _err(exc)
        return Response({'reported': True})


# -- staff ----------------------------------------------------------------------

class AdminRoomsView(APIView):
    """GET /api/admin/chat/rooms/ — every room with totals, hidden and reported
    counts, plus current mutes; POST — create a room."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response({'results': rooms.room_rows(player_id=None, staff=True), 'mutes': rooms.mutes(),
                         'audiences': [{'id': a.value, 'label': a.label} for a in ChatRoom.Audience]})

    def post(self, request):
        try:
            room = rooms.save_room(None, request.data, by=request.user.get_username(), request=request)
        except rooms.ChatError as exc:
            return _err(exc)
        return Response({'id': room.id, 'slug': room.slug}, status=status.HTTP_201_CREATED)


class AdminRoomView(APIView):
    """PATCH /api/admin/chat/rooms/<id>/ — edit; DELETE — remove the room and its messages (superuser)."""
    permission_classes = [IsAdminUser]

    def patch(self, request, pk: int):
        room = ChatRoom.objects.filter(pk=pk).first()
        if room is None:
            return Response({'detail': 'Room not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            rooms.save_room(room, request.data, by=request.user.get_username(), request=request)
        except rooms.ChatError as exc:
            return _err(exc)
        return Response({'id': room.id, 'slug': room.slug})

    def delete(self, request, pk: int):
        if not request.user.is_superuser:
            return Response({'detail': 'Only a superuser can delete a room.'}, status=status.HTTP_403_FORBIDDEN)
        room = ChatRoom.objects.filter(pk=pk).first()
        if room is None:
            return Response({'detail': 'Room not found.'}, status=status.HTTP_404_NOT_FOUND)
        rooms.delete_room(room, by=request.user.get_username(), request=request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class AdminRoomMessagesView(APIView):
    """GET /api/admin/chat/rooms/<id>/messages/?after=&before=&only=hidden|reported
    — everything, hidden messages included; POST {body, reply_to?} — post as staff."""
    permission_classes = [IsAdminUser]

    def _room(self, pk: int):
        return ChatRoom.objects.filter(pk=pk).first()

    def get(self, request, pk: int):
        room = self._room(pk)
        if room is None:
            return Response({'detail': 'Room not found.'}, status=status.HTTP_404_NOT_FOUND)
        after, before = _int(request.query_params.get('after')), _int(request.query_params.get('before'))
        only = request.query_params.get('only') or ''
        page = rooms.messages(room, staff=True, after=after, before=before, only=only)
        return Response({'results': [rooms.message_row(m, staff=True) for m in page],
                         'has_more': after is None and len(page) == rooms.PAGE})

    def post(self, request, pk: int):
        room = self._room(pk)
        if room is None:
            return Response({'detail': 'Room not found.'}, status=status.HTTP_404_NOT_FOUND)
        try:
            message = rooms.staff_post(room=room, body=request.data.get('body'), staff_name=_staff_name(request),
                                       reply_to=request.data.get('reply_to'))
        except rooms.ChatError as exc:
            return _err(exc)
        return Response(rooms.message_row(message, staff=True), status=status.HTTP_201_CREATED)


class AdminModerateView(APIView):
    """POST /api/admin/chat/moderate/ {ids: [..], action: hide|unhide|delete|pin|unpin, reason?}."""
    permission_classes = [IsAdminUser]

    def post(self, request):
        ids = request.data.get('ids')
        if not isinstance(ids, list) or not ids or not all(isinstance(i, int) and not isinstance(i, bool) for i in ids):
            return Response({'detail': 'Choose at least one message.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            result = rooms.moderate(ids, action=str(request.data.get('action') or ''), by=request.user.get_username(),
                                    reason=str(request.data.get('reason') or ''), request=request)
        except rooms.ChatError as exc:
            return _err(exc)
        return Response(result)


class AdminMutesView(APIView):
    """POST /api/admin/chat/mutes/ {player_id, minutes?, reason?} — mute (no minutes = until lifted)."""
    permission_classes = [IsAdminUser]

    def post(self, request):
        player_id, minutes = _int(request.data.get('player_id')), _int(request.data.get('minutes'))
        if player_id is None:
            return Response({'detail': 'Choose a player.'}, status=status.HTTP_400_BAD_REQUEST)
        try:
            rooms.mute(player_id=player_id, minutes=minutes, reason=str(request.data.get('reason') or ''),
                       by=request.user.get_username(), request=request)
        except rooms.ChatError as exc:
            return _err(exc)
        return Response({'mutes': rooms.mutes()}, status=status.HTTP_201_CREATED)


class AdminMuteView(APIView):
    """DELETE /api/admin/chat/mutes/<player_id>/ — lift a mute."""
    permission_classes = [IsAdminUser]

    def delete(self, request, player_id: int):
        rooms.unmute(player_id=player_id, by=request.user.get_username(), request=request)
        return Response({'mutes': rooms.mutes()})
