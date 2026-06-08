"""accounts transport — views move data; all logic is in services."""
from __future__ import annotations

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken


class AuthRateThrottle(AnonRateThrottle):
    rate = '10/minute'
    scope = 'auth'

from . import services
from .models import Player
from .serializers import PlayerSerializer, RegisterSerializer


class RegisterView(APIView):
    permission_classes = [AllowAny]
    throttle_classes = [AuthRateThrottle]

    def post(self, request):
        ser = RegisterSerializer(data=request.data)
        if not ser.is_valid():
            return Response(ser.errors, status=status.HTTP_400_BAD_REQUEST)
        d = ser.validated_data
        try:
            player = services.register_player(
                username=d['username'],
                email=d['email'],
                password=d['password'],
                currency=d.get('currency', 'USD'),
            )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(PlayerSerializer(player).data, status=status.HTTP_201_CREATED)


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            token = RefreshToken(request.data['refresh'])
            token.blacklist()
        except (KeyError, TokenError):
            return Response({'detail': 'invalid or missing refresh token'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ResponsibleGamblingView(APIView):
    """GET/PATCH /api/players/me/rg/ — deposit limits and self-exclusion."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        player = services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response({
            'deposit_limit_daily': str(player.deposit_limit_daily) if player.deposit_limit_daily is not None else None,
            'self_excluded': player.self_excluded,
            'exclusion_ends_at': player.exclusion_ends_at,
        })

    def patch(self, request):
        player = services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)
        if 'deposit_limit_daily' in request.data:
            try:
                player = services.set_deposit_limit(player.id, request.data['deposit_limit_daily'])
            except ValueError as exc:
                return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'deposit_limit_daily': str(player.deposit_limit_daily) if player.deposit_limit_daily is not None else None,
            'self_excluded': player.self_excluded,
            'exclusion_ends_at': player.exclusion_ends_at,
        })


class SelfExcludeView(APIView):
    """POST /api/players/me/self-exclude/ — initiate a cooling-off period."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        player = services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)
        days = request.data.get('days')
        try:
            days_int = int(days) if days is not None else None
        except (ValueError, TypeError):
            return Response({'detail': 'days must be an integer'}, status=status.HTTP_400_BAD_REQUEST)
        player = services.self_exclude(player.id, days=days_int)
        return Response({
            'self_excluded': player.self_excluded,
            'exclusion_ends_at': player.exclusion_ends_at,
            'detail': 'Self-exclusion applied. You can contact support to review this.',
        })


class PlayerViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Player.objects.all()
    serializer_class = PlayerSerializer

    @action(detail=False, methods=['get'], permission_classes=[IsAuthenticated])
    def me(self, request):
        player = services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player profile not found'}, status=status.HTTP_404_NOT_FOUND)
        return Response(self.get_serializer(player).data)
