"""sportsbook transport — views move data; placement logic lives in services."""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Prefetch, Q
from rest_framework import mixins, status, viewsets
from rest_framework.pagination import PageNumberPagination
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as accounts_services
from apps.wallet.services import InsufficientFunds

from . import booking as booking_services
from . import cashout as cashout_services
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
        qs = qs.select_related('home_team', 'away_team', 'league').annotate(
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


def _cash_out_response(request, kind: str, pk):
    """POST …/<id>/cashout/ {expected, amount?} — take the cash-out offer."""
    from decimal import Decimal, InvalidOperation
    player = accounts_services.get_current_player(request)
    if player is None:
        return Response({'detail': 'Player not found.'}, status=status.HTTP_404_NOT_FOUND)
    try:
        expected = Decimal(str(request.data.get('expected')))
        raw_amount = request.data.get('amount')
        amount = Decimal(str(raw_amount)) if raw_amount not in (None, '') else None
        if expected <= 0 or (amount is not None and amount <= 0):
            raise InvalidOperation
    except (InvalidOperation, ValueError, TypeError):
        return Response({'detail': 'Send the cash-out value you accepted.'}, status=status.HTTP_400_BAD_REQUEST)
    try:
        ticket, record = cashout_services.cash_out(
            kind=kind, ticket_id=int(pk), player_id=player.id, expected=expected, amount=amount,
        )
    except cashout_services.CashoutChanged as exc:
        return Response({'detail': str(exc), 'code': 'cashout_changed', 'value': str(exc.value)},
                        status=status.HTTP_409_CONFLICT)
    except cashout_services.CashoutUnavailable as exc:
        return Response({'detail': str(exc), 'code': 'cashout_unavailable'}, status=status.HTTP_409_CONFLICT)
    serializer = BetSerializer if kind == 'bet' else BetSlipSerializer
    from apps.wallet import services as wallet_services
    return Response({
        'paid': str(record.amount), 'full': record.full,
        'balance': str(wallet_services.get_balance_dto(player.id).balance),
        'ticket': serializer(ticket, context={'request': request}).data,
    })


class BetViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    serializer_class = BetSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        player = accounts_services.get_current_player(self.request)
        if player is None:
            return Bet.objects.none()
        return (
            Bet.objects.filter(player_id=player.id)
            .select_related('outcome_ref__market', 'event_ref').order_by('-placed_at')
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

    @action(detail=True, methods=['post'])
    def cashout(self, request, pk=None):
        return _cash_out_response(request, 'bet', pk)


class BetSlipViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Accumulator slips for the authenticated player."""
    serializer_class = BetSlipSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        player = accounts_services.get_current_player(self.request)
        if player is None:
            return BetSlip.objects.none()
        return BetSlip.objects.filter(player_id=player.id).prefetch_related(
            Prefetch('legs', queryset=BetLeg.objects.select_related('outcome_ref__market', 'event_ref')),
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

    @action(detail=True, methods=['post'])
    def cashout(self, request, pk=None):
        return _cash_out_response(request, 'slip', pk)


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


class BookingCodeCreateView(APIView):
    """POST /api/booking-codes/ {selections: [{event_id, selection} | {outcome_id}]}
    -> a short code anyone can load. Guests may book codes too."""
    permission_classes = [AllowAny]

    def post(self, request):
        player = accounts_services.get_current_player(request)
        try:
            booking = booking_services.create_booking(
                request.data.get('selections'), player_id=player.id if player else None,
            )
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(booking_services.booking_payload(booking), status=status.HTTP_201_CREATED)


class BookingCodeDetailView(APIView):
    """GET /api/booking-codes/<code>/ -> the picks with current prices."""
    permission_classes = [AllowAny]

    def get(self, request, code: str):
        payload = booking_services.load_booking(code)
        if payload is None:
            return Response({'detail': 'Booking code not found.'}, status=status.HTTP_404_NOT_FOUND)
        return Response(payload)


class MultiBetBonusView(APIView):
    """GET /api/multibet-bonus/ -> the accumulator bonus ladder."""
    permission_classes = [AllowAny]

    def get(self, request):
        return Response(services.multibet_bonus_info())


class CashoutOffersView(APIView):
    """GET /api/cashout/offers/?bets=1,2&slips=3 — current cash-out offers on
    the player's open tickets, polled while a ticket is on screen."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import CashoutSettings
        player = accounts_services.get_current_player(request)
        if player is None:
            return Response({'bets': {}, 'slips': {}})

        def ids(name):
            return [int(v) for v in request.query_params.get(name, '').split(',') if v.strip().isdigit()][:50]

        cfg = CashoutSettings.load()
        bets = Bet.objects.filter(player_id=player.id, pk__in=ids('bets')).select_related(
            'event_ref', 'outcome_ref__market__event')
        slips = BetSlip.objects.filter(player_id=player.id, pk__in=ids('slips')).prefetch_related(
            Prefetch('legs', queryset=BetLeg.objects.select_related('event_ref', 'outcome_ref__market__event')))
        return Response({
            'bets': {b.id: cashout_services.bet_offer(b, cfg).as_dict() for b in bets},
            'slips': {sl.id: cashout_services.slip_offer(sl, cfg).as_dict() for sl in slips},
        })


class AdminCashoutSettingsView(APIView):
    """GET/PUT /api/admin/sportsbook/cashout/ — cash-out switches and margin,
    plus what has been cashed out (today and all time)."""
    permission_classes = [IsAdminUser]

    def _payload(self):
        from django.db.models import Sum
        from django.utils import timezone
        from .models import Cashout, CashoutSettings
        cfg = CashoutSettings.load()
        today = timezone.localdate()
        agg = lambda qs: qs.aggregate(n=Count('id'), total=Sum('amount'))  # noqa: E731
        t, a = agg(Cashout.objects.filter(created_at__date=today)), agg(Cashout.objects.all())
        return {
            'enabled': cfg.enabled, 'allow_partial': cfg.allow_partial, 'in_play': cfg.in_play,
            'margin_percent': f'{cfg.margin_percent:.2f}', 'min_amount': f'{cfg.min_amount:.2f}',
            'updated_at': cfg.updated_at,
            'stats': {
                'today': {'count': t['n'], 'total': str(t['total'] or 0)},
                'all_time': {'count': a['n'], 'total': str(a['total'] or 0)},
            },
        }

    def get(self, request):
        return Response(self._payload())

    def put(self, request):
        from decimal import Decimal, InvalidOperation
        from .models import CashoutSettings
        cfg = CashoutSettings.load()
        data = request.data
        for flag in ('enabled', 'allow_partial', 'in_play'):
            if flag in data:
                setattr(cfg, flag, bool(data[flag]))
        try:
            if 'margin_percent' in data:
                margin = Decimal(str(data['margin_percent']))
                if not Decimal('0') <= margin <= Decimal('50'):
                    raise ValueError('The margin must be between 0% and 50%.')
                cfg.margin_percent = margin
            if 'min_amount' in data:
                minimum = Decimal(str(data['min_amount']))
                if minimum < Decimal('0.01'):
                    raise ValueError('The minimum must be at least $0.01.')
                cfg.min_amount = minimum
        except InvalidOperation:
            return Response({'detail': 'Enter numbers for the margin and minimum.'}, status=status.HTTP_400_BAD_REQUEST)
        except ValueError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        cfg.save()
        accounts_services.audit(None, 'cashout_settings', request,
                                enabled=cfg.enabled, margin=str(cfg.margin_percent))
        return Response(self._payload())


class AdminTicketsView(APIView):
    """GET /api/admin/tickets/?player_id=&q=&status=&kind=single|multiple
    — every player's tickets, singles and multiples together, newest first.
    `q` takes a ticket number as players see it (S12 / M5), a username or an email."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        import re

        from django.db.models import Q, Sum

        from apps.accounts.models import Player

        params = request.query_params
        singles, multis = Bet.objects.all(), BetSlip.objects.prefetch_related('legs')
        if params.get('player_id'):
            singles, multis = singles.filter(player_id=params['player_id']), multis.filter(player_id=params['player_id'])
        q = (params.get('q') or '').strip().lstrip('#')
        ticket = re.fullmatch(r'([SsMm])(\d+)', q)
        if ticket:
            pk = int(ticket.group(2))
            singles = singles.filter(pk=pk) if ticket.group(1).lower() == 's' else singles.none()
            multis = multis.filter(pk=pk) if ticket.group(1).lower() == 'm' else multis.none()
        elif q:
            ids = list(Player.objects.filter(Q(username__icontains=q) | Q(email__icontains=q)).values_list('id', flat=True)[:200])
            singles, multis = singles.filter(player_id__in=ids), multis.filter(player_id__in=ids)
        if params.get('status'):
            singles, multis = singles.filter(status=params['status']), multis.filter(status=params['status'])
        kind = params.get('kind')
        if kind == 'single':
            multis = multis.none()
        elif kind == 'multiple':
            singles = singles.none()

        rows = [{**BetSerializer(b, context={'request': request}).data, 'kind': 'single', 'ticket': f'S{b.id}',
                 'player_id': b.player_id} for b in singles.order_by('-placed_at')[:150]]
        rows += [{**BetSlipSerializer(s, context={'request': request}).data, 'kind': 'multiple', 'ticket': f'M{s.id}',
                  'player_id': s.player_id} for s in multis.order_by('-placed_at')[:150]]
        rows.sort(key=lambda r: r['placed_at'], reverse=True)
        rows = rows[:150]
        names = dict(Player.objects.filter(id__in={r['player_id'] for r in rows}).values_list('id', 'username'))
        for r in rows:
            r['username'] = names.get(r['player_id'], '(deleted)')

        summary = None
        if params.get('player_id'):
            def totals(qs):
                return qs.aggregate(n=Count('id'), staked=Sum('stake'), returned=Sum('payout'), cashed=Sum('cashout_paid'))
            a, b = totals(Bet.objects.filter(player_id=params['player_id'])), totals(BetSlip.objects.filter(player_id=params['player_id']))
            zero = Decimal('0')
            staked = (a['staked'] or zero) + (b['staked'] or zero)
            returned = sum((x or zero) for x in (a['returned'], b['returned'], a['cashed'], b['cashed']))
            summary = {'tickets': (a['n'] or 0) + (b['n'] or 0), 'staked': f'{staked:.2f}', 'returned': f'{returned:.2f}',
                       'open': Bet.objects.filter(player_id=params['player_id'], status='open').count()
                       + BetSlip.objects.filter(player_id=params['player_id'], status='open').count()}
        return Response({'results': rows, 'summary': summary})
