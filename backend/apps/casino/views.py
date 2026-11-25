"""casino transport — game catalog, instant play, round history."""
from __future__ import annotations

from decimal import Decimal, InvalidOperation

from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response

from apps.accounts import services as accounts_services
from apps.wallet import services as wallet_services
from apps.wallet.services import InsufficientFunds

from . import services
from .models import CrashRound, Game, GameRound
from .serializers import (
    CrashHistorySerializer,
    CrashRoundSerializer,
    GameRoundSerializer,
    GameSerializer,
    RecentWinSerializer,
)


class GamePagination(PageNumberPagination):
    page_size = 25
    page_size_query_param = 'page_size'     # the lobby loads the whole catalogue (500+) at once
    max_page_size = 1000


class GameViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    queryset = Game.objects.filter(is_active=True)
    serializer_class = GameSerializer
    permission_classes = [AllowAny]
    pagination_class = GamePagination

    def get_queryset(self):
        qs = super().get_queryset()
        category = self.request.query_params.get('category')
        if category:
            qs = qs.filter(category=category)
        # Playable games first, then the coming-soon ones.
        return qs.order_by('coming_soon', 'name')

    @action(detail=True, methods=['post', 'delete'], permission_classes=[IsAuthenticated], url_path='notify')
    def notify(self, request, pk=None):
        """POST: tell me when this coming-soon game is ready. DELETE: never mind."""
        player = accounts_services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)
        if request.method == 'DELETE':
            services.leave_waitlist(player_id=player.id, game_id=int(pk))
            return Response({'waiting': False})
        try:
            services.join_waitlist(player_id=player.id, game_id=int(pk))
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({'waiting': True})

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated], url_path='play')
    def play(self, request, pk=None):
        """POST /api/casino/games/{id}/play/ — instant spin: debit, settle, return outcome."""
        player = accounts_services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)
        if Game.objects.filter(pk=pk, coming_soon=True).exists():
            return Response({'detail': 'This game is coming soon. Tap Notify me and we’ll tell you when it’s ready.'},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            stake = Decimal(str(request.data.get('stake', '0')))
            if stake <= 0:
                raise ValueError('stake must be positive')
        except (InvalidOperation, ValueError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Responsible gambling check.
        try:
            accounts_services.check_responsible_gambling(player)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)

        try:
            rnd = services.start_round(player_id=player.id, game_id=int(pk), stake=stake,
                                       wallet=request.data.get('wallet'))
        except InsufficientFunds as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_402_PAYMENT_REQUIRED)
        except Exception as exc:  # noqa: BLE001
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        # Settle immediately using the stub provider outcome.
        from .clients import CasinoProviderClient
        outcome = CasinoProviderClient().settle_round(rnd.provider_round_ref, stake=stake)
        rnd = services.settle_round(rnd.id, win=outcome.win)

        balance_dto = wallet_services.get_balance_dto(player.id)
        return Response({
            'round': GameRoundSerializer(rnd).data,
            'win': str(rnd.win),
            'balance': str(balance_dto.balance),
            'currency': balance_dto.currency,
        }, status=status.HTTP_201_CREATED)


class GameRoundViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    serializer_class = GameRoundSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        player = accounts_services.get_current_player(self.request)
        if player is None:
            return GameRound.objects.none()
        return GameRound.objects.filter(player_id=player.id).order_by('-created_at')[:50]

    @action(detail=False, methods=['get'], permission_classes=[AllowAny], url_path='recent-wins')
    def recent_wins(self, request):
        """GET /api/casino/rounds/recent-wins/ — public win ticker (no player identity)."""
        qs = GameRound.objects.filter(status='settled', win__gt=0).select_related('game').order_by('-created_at')[:10]
        return Response(RecentWinSerializer(qs, many=True).data)


class CrashViewSet(viewsets.ViewSet):
    """Aviator-style crash game: place a bet, then cash out before the bust."""

    permission_classes = [IsAuthenticated]

    def create(self, request):
        """POST /api/casino/crash/ — place a crash bet (debits the stake)."""
        player = accounts_services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)

        try:
            stake = Decimal(str(request.data.get('stake', '0')))
            if stake <= 0:
                raise ValueError('stake must be positive')
        except (InvalidOperation, ValueError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        try:
            accounts_services.check_responsible_gambling(player)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)

        try:
            rnd = services.place_crash_bet(player_id=player.id, stake=stake, wallet=request.data.get('wallet'))
        except InsufficientFunds as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_402_PAYMENT_REQUIRED)
        except Exception as exc:  # noqa: BLE001
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(CrashRoundSerializer(rnd).data, status=status.HTTP_201_CREATED)

    @action(detail=True, methods=['post'], url_path='cashout')
    def cashout(self, request, pk=None):
        """POST /api/casino/crash/{id}/cashout/ — cash out (optional `multiplier` target)."""
        player = accounts_services.get_current_player(request)
        if player is None:
            return Response({'detail': 'player not found'}, status=status.HTTP_404_NOT_FOUND)

        target = None
        raw_target = request.data.get('multiplier')
        if raw_target is not None:
            try:
                target = Decimal(str(raw_target))
            except InvalidOperation:
                return Response({'detail': 'multiplier is malformed'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            rnd = services.cashout_crash(player_id=player.id, crash_id=int(pk), target=target)
        except CrashRound.DoesNotExist:
            return Response({'detail': 'round not found'}, status=status.HTTP_404_NOT_FOUND)

        balance_dto = wallet_services.get_balance_dto(player.id)
        return Response({
            'round': CrashRoundSerializer(rnd).data,
            'balance': str(balance_dto.balance),
            'currency': balance_dto.currency,
        })

    @action(detail=False, methods=['get'], permission_classes=[AllowAny], url_path='history')
    def history(self, request):
        """GET /api/casino/crash/history/ — recent settled crash multipliers (public)."""
        qs = CrashRound.objects.exclude(status=CrashRound.Status.RUNNING).order_by('-created_at')[:20]
        return Response(CrashHistorySerializer(qs, many=True).data)


class MyWaitlistView(APIView):
    """GET /api/casino/waitlist/ — the coming-soon games this player asked to hear about."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import GameWaitlist
        player = accounts_services.get_current_player(request)
        ids = list(GameWaitlist.objects.filter(player_id=player.id, notified_at__isnull=True).values_list('game_id', flat=True)) \
            if player else []
        return Response({'games': ids})


class AdminGamesView(APIView):
    """GET /api/admin/casino/games/?q=&category=&status=soon|live — the catalogue with how many
    players wait for each coming-soon game."""
    permission_classes = [IsAdminUser]
    PAGE = 100

    def get(self, request):
        from django.db.models import Count, Q
        qs = Game.objects.annotate(waiting=Count('waitlist', filter=Q(waitlist__notified_at__isnull=True)))
        q = (request.query_params.get('q') or '').strip()
        if q:
            qs = qs.filter(Q(name__icontains=q) | Q(provider__icontains=q))
        if request.query_params.get('category'):
            qs = qs.filter(category=request.query_params['category'])
        st = request.query_params.get('status')
        if st == 'soon':
            qs = qs.filter(coming_soon=True)
        elif st == 'live':
            qs = qs.filter(coming_soon=False)
        qs = qs.order_by('-waiting', 'name')
        try:
            page = max(1, int(request.query_params.get('page') or 1))
        except ValueError:
            page = 1
        total = qs.count()
        rows = qs[(page - 1) * self.PAGE: page * self.PAGE]
        return Response({
            'count': total, 'page': page, 'page_size': self.PAGE,
            'totals': {'all': Game.objects.count(), 'soon': Game.objects.filter(coming_soon=True).count(),
                       'waiting': _waiting_total()},
            'categories': Game.Category.choices,
            'results': [{'id': g.id, 'name': g.name, 'provider': g.provider, 'category': g.category, 'slug': g.slug,
                         'is_active': g.is_active, 'coming_soon': g.coming_soon, 'image_url': g.image_url,
                         'waiting': g.waiting} for g in rows],
        })


def _waiting_total() -> int:
    from .models import GameWaitlist
    return GameWaitlist.objects.filter(notified_at__isnull=True).count()


class AdminGameDetailView(APIView):
    """PATCH /api/admin/casino/games/<id>/ {coming_soon, is_active, name, provider, image_url}.
    Switching coming_soon off launches the game and notifies everyone waiting."""
    permission_classes = [IsAdminUser]

    def patch(self, request, pk: int):
        game = Game.objects.filter(pk=pk).first()
        if game is None:
            return Response({'detail': 'Not found.'}, status=status.HTTP_404_NOT_FOUND)
        changed = []
        for f in ('name', 'provider', 'image_url'):
            if f in request.data:
                setattr(game, f, str(request.data[f] or '').strip()[:500 if f == 'image_url' else 200])
                changed.append(f)
        if 'is_active' in request.data:
            game.is_active = bool(request.data['is_active'])
            changed.append('is_active')
        if game.name == '':
            return Response({'detail': 'A game needs a name.'}, status=status.HTTP_400_BAD_REQUEST)
        launching = 'coming_soon' in request.data and not request.data['coming_soon'] and game.coming_soon
        if 'coming_soon' in request.data and request.data['coming_soon'] and not game.coming_soon:
            game.coming_soon = True
            changed.append('coming_soon')
        if changed:
            game.save(update_fields=changed)
        notified = services.launch(game) if launching else 0
        accounts_services.audit(None, 'casino_game_update', request, game=game.slug,
                                launched=launching, notified=notified, changed=','.join(changed))
        return Response({'id': game.id, 'coming_soon': game.coming_soon, 'is_active': game.is_active, 'notified': notified})
