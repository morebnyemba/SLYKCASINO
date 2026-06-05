"""wallet transport — read-only balance endpoint for the acting player."""
from __future__ import annotations

from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as accounts_services

from . import services


class WalletView(APIView):
    """GET /api/wallet/ -> current player's balance (preserves the FE contract)."""

    def get(self, request):
        player = accounts_services.get_current_player(request)
        if player is None:
            return Response({'balance': 0, 'currency': 'USD'})
        dto = services.get_balance_dto(player.id)
        return Response({'balance': str(dto.balance), 'currency': dto.currency})
