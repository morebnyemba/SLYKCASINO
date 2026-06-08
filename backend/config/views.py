"""Composition-root transport: health + cross-domain admin stats.

Aggregating counts across bounded contexts is a legitimate composition-root
concern (no single domain owns it), so it lives here rather than in any app.
"""
from __future__ import annotations

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny, IsAdminUser
from rest_framework.response import Response

from apps.accounts.models import Player
from apps.livechat.models import ChatMessage
from apps.promotions.models import Promotion
from apps.sportsbook.models import Bet


@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    return Response({'status': 'ok'})


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_stats(request):
    return Response({
        'online_players': Player.objects.count(),
        'open_bets': Bet.objects.filter(status=Bet.Status.OPEN).count(),
        'active_promotions': Promotion.objects.filter(active=True).count(),
        'open_chats': ChatMessage.objects.values('channel').distinct().count(),
    })
