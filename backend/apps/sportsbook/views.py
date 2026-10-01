"""sportsbook transport — views move data; placement logic lives in services."""
from __future__ import annotations

from django.db.models import Count, Prefetch, Q
from rest_framework import mixins, status, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response

from apps.accounts import services as accounts_services
from apps.wallet.services import InsufficientFunds

from . import services
from .dtos import AccumulatorRequestDTO, BetRequestDTO
from .models import Bet, BetLeg, BetSlip, Event, Market
from .serializers import BetSerializer, BetSlipSerializer, EventDetailSerializer, EventSerializer


class EventPagination(PageNumberPagination):
    """25 per page by default; listings can ask for a full board with ?page_size=."""
    page_size = 25
    page_size_query_param = 'page_size'
    max_page_size = 500


class EventViewSet(viewsets.ModelViewSet):
    serializer_class = EventSerializer
    pagination_class = EventPagination
    # Events are publicly browsable; mutations require auth.
    permission_classes = [AllowAny]

    def get_queryset(self):
        params = self.request.query_params
        featured = params.get('featured') == 'true'
        upcoming = params.get('upcoming') == 'true'
        priced = {'true': True, 'false': False}.get(params.get('priced', ''))
        qs = services.list_events(
            featured=featured or None, sport=params.get('sport'), upcoming=upcoming, priced=priced,
        )
        # `id` last so equal kick-off/name rows page deterministically (no repeats/gaps).
        ordering = qs.query.order_by or [*Event._meta.ordering, 'id']
        qs = qs.select_related('home_team', 'away_team').annotate(
            markets_count=Count('markets', filter=Q(markets__is_open=True), distinct=True),
        ).order_by(*ordering)  # aggregation drops Meta.ordering, so re-apply it
        if self.action == 'retrieve':
            qs = qs.prefetch_related(Prefetch(
                'markets', queryset=Market.objects.prefetch_related('outcomes'),
            ))
        return qs

    def get_serializer_class(self):
        return EventDetailSerializer if self.action == 'retrieve' else EventSerializer

    def get_permissions(self):
        if self.action in (
            'create', 'update', 'partial_update', 'destroy', 'settle', 'settle_score', 'settle_market',
        ):
            return [IsAdminUser()]
        return [AllowAny()]

    @action(detail=False, methods=['get'], url_path='prices')
    def prices(self, request):
        """Current prices for a bet slip: ?events=1,2&outcomes=5,6 (max 50 each)."""
        def ids(name):
            raw = request.query_params.get(name, '')
            return [int(v) for v in raw.split(',') if v.strip().isdigit()][:50]
        return Response(services.current_prices(event_ids=ids('events'), outcome_ids=ids('outcomes')))

    @action(detail=True, methods=['post'], url_path='settle-score')
    def settle_score(self, request, pk=None):
        """Record the final (90-minute) score and settle the 1X2 plus every market
        those facts decide. Takes {home, away, ht_home?, ht_away?} and optional
        corners_home/away, yellow_home/away, red_home/away for stats markets."""
        try:
            home, away = int(request.data['home']), int(request.data['away'])
            ht_home = request.data.get('ht_home')
            ht_away = request.data.get('ht_away')
            ht_home = int(ht_home) if ht_home not in (None, '') else None
            ht_away = int(ht_away) if ht_away not in (None, '') else None
            if min(home, away) < 0 or (ht_home is not None and ht_home < 0) or (ht_away is not None and ht_away < 0):
                raise ValueError('scores must be non-negative')
            if (ht_home is None) != (ht_away is None):
                raise ValueError('give both half-time scores or neither')
            def pair(prefix):
                h, a = request.data.get(f'{prefix}_home'), request.data.get(f'{prefix}_away')
                if h in (None, '') and a in (None, ''):
                    return None
                if h in (None, '') or a in (None, '') or int(h) < 0 or int(a) < 0:
                    raise ValueError(f'give both {prefix} counts (non-negative) or neither')
                return int(h), int(a)
            count = services.settle_event_from_score(
                int(pk), home=home, away=away, ht_home=ht_home, ht_away=ht_away,
                corners=pair('corners'), yellow=pair('yellow'), red=pair('red'),
            )
        except (KeyError, TypeError, ValueError) as exc:
            return Response({'detail': str(exc) or 'home and away are required'}, status=status.HTTP_400_BAD_REQUEST)
        except Event.DoesNotExist:
            return Response({'detail': 'Event not found'}, status=status.HTTP_404_NOT_FOUND)
        from apps.accounts.services import audit
        audit(None, 'event_settled_score', request, event_id=int(pk), home=home, away=away, bets_settled=count)
        return Response({'event': int(pk), 'score': f'{home}-{away}', 'bets_settled': count})

    @action(detail=True, methods=['post'], url_path=r'markets/(?P<market_id>[0-9]+)/settle')
    def settle_market(self, request, pk=None, market_id=None):
        """Operator settlement of one market: {winners: [outcome_id, ...]} or {void: true}."""
        if not Market.objects.filter(pk=market_id, event_id=pk).exists():
            return Response({'detail': 'Market not found'}, status=status.HTTP_404_NOT_FOUND)
        try:
            winners = [int(w) for w in (request.data.get('winners') or [])]
            count = services.settle_market_manually(
                int(market_id), winners=winners, void=bool(request.data.get('void')),
            )
        except (TypeError, ValueError) as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        from apps.accounts.services import audit
        audit(None, 'market_settled', request, event_id=int(pk), market_id=int(market_id), bets_settled=count)
        return Response({'market': int(market_id), 'bets_settled': count})

    @action(detail=True, methods=['post'], url_path='settle')
    def settle(self, request, pk=None):
        """Settle every open bet on this event from one result.
        Takes {result: 'home'|'draw'|'away'|'void'}."""
        result = request.data.get('result', '')
        try:
            count = services.settle_event(int(pk), result)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        from apps.accounts.services import audit
        audit(None, 'event_settled', request, event_id=int(pk), result=result, bets_settled=count)
        return Response({'event': int(pk), 'result': result, 'bets_settled': count})


class BetViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = BetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        player = accounts_services.get_current_player(self.request)
        if player is None:
            return Bet.objects.none()
        return (
            Bet.objects.filter(player_id=player.id)
            .select_related('outcome_ref__market').order_by('-placed_at')
        )

    def create(self, request, *args, **kwargs):
        player = accounts_services.get_current_player(request)
        if player:
            try:
                accounts_services.check_responsible_gambling(player)
            except ValueError as exc:
                return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        try:
            dto = BetRequestDTO(
                player_id=player.id if player else None,
                event=request.data.get('event'),
                event_id=request.data.get('event_id'),
                selection=request.data.get('selection') or 'home',
                outcome_id=request.data.get('outcome_id'),
                stake=request.data.get('stake'),
                odds=request.data.get('odds'),
            )
            bet = services.place_bet(
                event=dto.event, stake=dto.stake, odds=dto.odds, player_id=dto.player_id,
                event_id=dto.event_id, selection=dto.selection, outcome_id=dto.outcome_id,
            )
        except services.OddsChanged as exc:
            return Response(
                {
                    'detail': str(exc), 'code': 'odds_changed', 'odds': str(exc.current),
                    'outcome_id': exc.outcome_id, 'event_id': exc.event_id, 'selection': exc.selection,
                },
                status=status.HTTP_409_CONFLICT,
            )
        except services.SelectionUnavailable as exc:
            return Response({'detail': str(exc), 'code': 'suspended'}, status=status.HTTP_409_CONFLICT)
        except InsufficientFunds as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_402_PAYMENT_REQUIRED)
        except (ValueError, Exception) as exc:  # noqa: BLE001
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(bet).data, status=status.HTTP_201_CREATED)


class BetSlipViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Accumulator slips for the authenticated player."""
    serializer_class = BetSlipSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        player = accounts_services.get_current_player(self.request)
        if player is None:
            return BetSlip.objects.none()
        return BetSlip.objects.filter(player_id=player.id).prefetch_related(
            Prefetch('legs', queryset=BetLeg.objects.select_related('outcome_ref__market')),
        ).order_by('-placed_at')

    def create(self, request, *args, **kwargs):
        player = accounts_services.get_current_player(request)
        if player:
            try:
                accounts_services.check_responsible_gambling(player)
            except ValueError as exc:
                return Response({'detail': str(exc)}, status=status.HTTP_403_FORBIDDEN)
        try:
            dto = AccumulatorRequestDTO(
                player_id=player.id if player else None,
                stake=request.data.get('stake'),
                legs=request.data.get('legs') or [],
            )
            slip = services.place_accumulator(
                stake=dto.stake,
                legs=[leg.model_dump() for leg in dto.legs],
                player_id=dto.player_id,
            )
        except services.OddsChanged as exc:
            return Response(
                {
                    'detail': str(exc), 'code': 'odds_changed', 'odds': str(exc.current),
                    'outcome_id': exc.outcome_id, 'event_id': exc.event_id, 'selection': exc.selection,
                },
                status=status.HTTP_409_CONFLICT,
            )
        except services.SelectionUnavailable as exc:
            return Response({'detail': str(exc), 'code': 'suspended'}, status=status.HTTP_409_CONFLICT)
        except InsufficientFunds as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_402_PAYMENT_REQUIRED)
        except (ValueError, Exception) as exc:  # noqa: BLE001
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(slip).data, status=status.HTTP_201_CREATED)


class AdminBetViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Staff-only view of all bets across all players."""
    serializer_class = BetSerializer
    permission_classes = [IsAdminUser]

    def get_queryset(self):
        qs = Bet.objects.order_by('-placed_at')
        status_filter = self.request.query_params.get('status')
        if status_filter:
            qs = qs.filter(status=status_filter)
        return qs[:200]

    @action(detail=True, methods=['post'], url_path='settle')
    def settle(self, request, pk=None):
        """Settle a bet. Takes {outcome: 'won'|'lost'|'void'}."""
        outcome = request.data.get('outcome', '')
        if outcome not in ('won', 'lost', 'void'):
            return Response(
                {'detail': "outcome must be 'won', 'lost', or 'void'"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            bet = services.settle_bet(int(pk), outcome)
        except Bet.DoesNotExist:
            return Response({'detail': 'Bet not found'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as exc:  # noqa: BLE001
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        # Audit
        from apps.accounts.services import audit
        audit(bet.player_id, 'bet_settled', request, bet_id=bet.id, outcome=outcome)
        return Response(self.get_serializer(bet).data)
