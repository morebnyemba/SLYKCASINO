"""affiliates transport — views move data; logic lives in services."""
from __future__ import annotations

from datetime import date, datetime, time

from django.db.models import Count
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import impersonation
from apps.accounts import services as accounts_services
from common.timeframes import TimeframeError

from . import services
from .pagination import AffiliatePagination
from .models import Affiliate, Commission, Payout, Referral
from .serializers import (
    AdminAffiliateSerializer, AdminPayoutSerializer, AffiliateSerializer, CommissionSerializer, PayoutSerializer,
    ProgrammeSerializer,
)


def _money_json(value):
    """Decimals as '12.30' strings (like the serializers), nested."""
    from decimal import Decimal
    if isinstance(value, Decimal):
        return f'{value:.2f}'
    if isinstance(value, dict):
        return {k: _money_json(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_money_json(v) for v in value]
    return value


def _affiliates_matching(q: str):
    """Agents whose code or username contains `q` (staff search)."""
    from django.db.models import Q

    from apps.accounts.models import Player
    players = Player.objects.filter(username__icontains=q).values_list('id', flat=True)
    return Affiliate.objects.filter(Q(code__icontains=q) | Q(player_id__in=players)).values('pk')


def _player_or_403(request):
    player = accounts_services.get_current_player(request)
    if player is None:
        return None, Response({'detail': 'no player profile'}, status=status.HTTP_403_FORBIDDEN)
    return player, None


class MyAffiliateView(APIView):
    """GET: the player's affiliate account with dashboard stats (404 if they
    haven't joined). POST: apply to join ({website?, code?})."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        player, denied = _player_or_403(request)
        if denied:
            return denied
        affiliate = services.get_for_player(player.id)
        if affiliate is None:
            return Response({'detail': 'not an affiliate'}, status=status.HTTP_404_NOT_FOUND)
        data = AffiliateSerializer(affiliate).data
        data['programme'] = _public_programme()
        if affiliate.status == Affiliate.Status.ACTIVE:
            data['stats'] = services.dashboard(affiliate, mask=not impersonation.is_impersonated(request))
            data['commissions'] = CommissionSerializer(affiliate.commissions.all()[:50], many=True).data
        if affiliate.status in (Affiliate.Status.ACTIVE, Affiliate.Status.SUSPENDED):
            data['balance'] = {k: str(v) for k, v in services.balance(affiliate).items()}
            data['payouts'] = PayoutSerializer(affiliate.payouts.all()[:50], many=True).data
            data['payout_options'] = services.payout_options(affiliate)
        return Response(data)

    def post(self, request):
        player, denied = _player_or_403(request)
        if denied:
            return denied
        try:
            affiliate = services.apply(
                player_id=player.id, website=str(request.data.get('website') or ''),
                code=str(request.data.get('code') or ''),
            )
        except services.AffiliateError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        accounts_services.audit(player.id, 'affiliate_applied', request, code=affiliate.code)
        return Response(AffiliateSerializer(affiliate).data, status=status.HTTP_201_CREATED)


def _analytics_response(request, affiliate):
    q = request.query_params
    try:
        data = services.affiliate_analytics(
            affiliate, q.get('frame') or 'today', start=q.get('start'), end=q.get('end'),
        )
    except TimeframeError as exc:
        return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response(data)


class MyPayoutsView(APIView):
    """POST /api/affiliates/me/payouts/ {amount, method, account_name?, account_number?, bank_name?}
    — withdraw from the affiliate balance (wallet: instant; mobile money/bank:
    sent by an operator)."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        player, denied = _player_or_403(request)
        if denied:
            return denied
        affiliate = services.get_for_player(player.id)
        if affiliate is None:
            return Response({'detail': 'not an affiliate'}, status=status.HTTP_404_NOT_FOUND)
        d = request.data
        try:
            payout = services.request_payout(
                affiliate_id=affiliate.id, amount=d.get('amount'), method=str(d.get('method') or ''),
                account_name=str(d.get('account_name') or ''), account_number=str(d.get('account_number') or ''),
                bank_name=str(d.get('bank_name') or ''),
            )
        except services.AffiliateError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({
            'payout': PayoutSerializer(payout).data,
            'balance': {k: str(v) for k, v in services.balance(affiliate).items()},
        }, status=status.HTTP_201_CREATED)


class AdminPayoutViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Staff: affiliate payout requests (?status=requested|paid|rejected), with
    mark-paid ({reference, note}) and reject ({note})."""
    serializer_class = AdminPayoutSerializer
    permission_classes = [IsAdminUser]
    pagination_class = AffiliatePagination

    def get_queryset(self):
        qs = Payout.objects.select_related('affiliate').order_by('-created_at')
        wanted = self.request.query_params.get('status')
        qs = qs.filter(status=wanted) if wanted else qs
        q = (self.request.query_params.get('q') or '').strip()
        return qs.filter(affiliate__in=_affiliates_matching(q)) if q else qs

    def get_serializer_context(self):
        from apps.accounts.models import Player
        ctx = super().get_serializer_context()
        ids = list(Affiliate.objects.values_list('player_id', flat=True))
        ctx['players'] = {p[0]: (p[1], p[2]) for p in Player.objects.filter(pk__in=ids).values_list('id', 'username', 'kyc_status')}
        return ctx

    def _done(self, payout):
        return Response(self.get_serializer(payout).data)

    @action(detail=True, methods=['post'], url_path='mark-paid')
    def mark_paid(self, request, pk=None):
        try:
            payout = services.mark_payout_paid(int(pk), reference=str(request.data.get('reference') or ''),
                                               note=str(request.data.get('note') or ''))
        except services.AffiliateError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        accounts_services.audit(payout.affiliate.player_id, 'affiliate_payout_paid', request, payout=payout.id,
                                amount=str(payout.amount), method=payout.method, reference=payout.reference)
        return self._done(payout)

    @action(detail=True, methods=['post'])
    def reject(self, request, pk=None):
        try:
            payout = services.reject_payout(int(pk), note=str(request.data.get('note') or ''))
        except services.AffiliateError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        accounts_services.audit(payout.affiliate.player_id, 'affiliate_payout_rejected', request, payout=payout.id,
                                amount=str(payout.amount), note=payout.note)
        return self._done(payout)


class MyCustomerTicketsView(APIView):
    """GET /affiliates/me/tickets/?status=open|won|lost|void&cursor= — every
    ticket the agent's players have placed, newest first."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        player, denied = _player_or_403(request)
        if denied:
            return denied
        affiliate = services.get_for_player(player.id)
        if affiliate is None or affiliate.status not in (Affiliate.Status.ACTIVE, Affiliate.Status.SUSPENDED):
            return Response({'detail': 'not an active affiliate'}, status=status.HTTP_404_NOT_FOUND)
        data = services.customer_tickets(affiliate, request.query_params, request,
                                         mask=not impersonation.is_impersonated(request))
        if data is None:
            return Response({'detail': 'Invalid cursor.'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(data)


class MyReportView(APIView):
    """GET /affiliates/me/report/?frame=today|yesterday|7d|30d|90d|this_month|
    last_month|this_year|custom[&start=YYYY-MM-DD&end=YYYY-MM-DD][&page=N] —
    the agent's customers' deposits, tickets, clicks, sign-ups and commission
    for one period (up to ten years back)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        player, denied = _player_or_403(request)
        if denied:
            return denied
        affiliate = services.get_for_player(player.id)
        if affiliate is None or affiliate.status not in (Affiliate.Status.ACTIVE, Affiliate.Status.SUSPENDED):
            return Response({'detail': 'not an active affiliate'}, status=status.HTTP_404_NOT_FOUND)
        q = request.query_params
        try:
            page = int(q.get('page') or 1)
        except ValueError:
            page = 1
        try:
            data = services.period_report(affiliate, q.get('frame') or 'today', start=q.get('start'), end=q.get('end'),
                                          page=page, mask=not impersonation.is_impersonated(request))
        except TimeframeError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(data)


class MyAffiliateAnalyticsView(APIView):
    """GET /affiliates/me/analytics/?frame=today|live|yesterday|7d|30d|90d|this_month|
    last_month|this_year|all[&start=YYYY-MM-DD&end=YYYY-MM-DD for frame=custom] —
    live KPIs, chart series, campaigns, top players and recent activity."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        player, denied = _player_or_403(request)
        if denied:
            return denied
        affiliate = services.get_for_player(player.id)
        if affiliate is None or affiliate.status not in (Affiliate.Status.ACTIVE, Affiliate.Status.SUSPENDED):
            return Response({'detail': 'not an active affiliate'}, status=status.HTTP_404_NOT_FOUND)
        return _analytics_response(request, affiliate)


def _public_programme() -> dict:
    """What affiliates (and would-be affiliates) are told about the programme."""
    p = services.get_programme()
    return {
        'welcome_bonus_percent': str(p.welcome_bonus_percent), 'welcome_bonus_cap': str(p.welcome_bonus_cap),
        'welcome_bonus_wagering': str(p.welcome_bonus_wagering), 'welcome_bonus_min_deposit': str(p.welcome_bonus_min_deposit),
        'cpa_min_turnover_multiple': str(p.cpa_min_turnover_multiple), 'negative_carryover': p.negative_carryover,
    }


class TermsView(APIView):
    """Public: the programme's default terms (for the join page) and the
    welcome bonus referred players get."""
    permission_classes = [AllowAny]

    def get(self, request):
        p = services.get_programme()
        return Response({
            'revshare_percent': str(p.default_revshare_percent),
            'cpa_amount': str(p.default_cpa_amount),
            'cpa_min_deposit': str(p.default_cpa_min_deposit),
            'cpa_percent': str(p.default_cpa_percent),
            'cpa_cap': str(p.default_cpa_cap),
            'programme': _public_programme(),
        })


class AdminProgrammeView(APIView):
    """GET/PUT /api/admin/affiliate-programme/ — programme-wide settings:
    referred players' welcome bonus, new affiliates' default terms, deposit
    commission qualification and losing-month carry-over."""
    permission_classes = [IsAdminUser]

    def get(self, request):
        return Response(ProgrammeSerializer(services.get_programme()).data)

    def put(self, request):
        fields = [*services.PROGRAMME_FIELDS, 'negative_carryover', 'external_payouts', 'auto_payout',
                  'auto_approve_commissions', 'lock_until_month_end']
        try:
            programme = services.update_programme(**{f: request.data.get(f) for f in fields})
        except (services.AffiliateError, ArithmeticError, ValueError) as exc:
            return Response({'detail': str(exc) or 'invalid value'}, status=status.HTTP_400_BAD_REQUEST)
        data = ProgrammeSerializer(programme).data
        accounts_services.audit(None, 'affiliate_programme', request,
                                **{k: str(v) for k, v in data.items() if k != 'updated_at'})
        return Response(data)


class ClickView(APIView):
    """Public: log a visit through an affiliate link ({code, campaign?, landing?})."""
    permission_classes = [AllowAny]
    authentication_classes = []

    def post(self, request):
        ok = services.record_click(
            str(request.data.get('code') or ''), campaign=str(request.data.get('campaign') or ''),
            landing=str(request.data.get('landing') or ''),
        )
        return Response({'tracked': ok})


class AdminAffiliateViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, viewsets.GenericViewSet):
    """Staff: every affiliate, with approve/suspend, terms and dashboards."""
    serializer_class = AdminAffiliateSerializer
    permission_classes = [IsAdminUser]
    pagination_class = AffiliatePagination

    def get_queryset(self):
        qs = Affiliate.objects.annotate(
            referrals_count=Count('referrals', distinct=True), clicks_count=Count('clicks', distinct=True),
        ).order_by('-created_at')
        wanted = self.request.query_params.get('status')
        qs = qs.filter(status=wanted) if wanted else qs
        q = (self.request.query_params.get('q') or '').strip()
        return qs.filter(pk__in=_affiliates_matching(q)) if q else qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ids = list(Affiliate.objects.values_list('player_id', flat=True))
        ctx['usernames'] = accounts_services.usernames_for(ids)
        return ctx

    def retrieve(self, request, *args, **kwargs):
        affiliate = self.get_object()
        data = self.get_serializer(affiliate).data
        data['stats'] = services.dashboard(affiliate, mask=False)
        return Response(data)

    @action(detail=True, methods=['get'], url_path='analytics')
    def analytics(self, request, pk=None):
        return _analytics_response(request, self.get_object())

    @action(detail=True, methods=['post'], url_path='status')
    def set_status(self, request, pk=None):
        try:
            affiliate = services.set_status(int(pk), str(request.data.get('status') or ''))
        except services.AffiliateError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        accounts_services.audit(affiliate.player_id, 'affiliate_status', request, status=affiliate.status)
        return Response(self.get_serializer(self.get_queryset().get(pk=affiliate.pk)).data)

    @action(detail=False, methods=['get'], url_path='crediting-health')
    def crediting_health(self, request):
        """Is the losing-ticket job running, and is any agent owed money?"""
        return Response(_money_json(services.crediting_health()))

    @action(detail=False, methods=['post'], url_path='credit-missed')
    def credit_missed_all(self, request):
        """Close every agent's completed days now, and credit any losing ticket from
        before the switch to net loss that was missed."""
        from . import netloss
        days = netloss.close_days()
        credited = services.catch_up_losing_tickets()
        accounts_services.audit(None, 'affiliate_credit_missed', request, credited=credited, days=days)
        return Response({'credited': credited, 'days': days})

    @action(detail=True, methods=['get'], url_path='statements')
    def statements(self, request, pk=None):
        """Each closed day: the customers' net loss, how it was worked out, and the commission."""
        from . import netloss
        affiliate = self.get_object()
        return Response(_money_json({
            'today': netloss.today_estimate(affiliate),
            'carry': services.carryover_balance(affiliate),
            'days': netloss.statements(affiliate),
        }))

    @action(detail=True, methods=['get'], url_path='tickets-audit')
    def tickets_audit(self, request, pk=None):
        """Each losing ticket of this agent's customers: credited, or why not."""
        try:
            days = max(1, min(int(request.query_params.get('days') or services.CATCH_UP_DAYS), 365))
        except ValueError:
            days = services.CATCH_UP_DAYS
        return Response(_money_json(services.ticket_audit(self.get_object(), days=days)))

    @action(detail=True, methods=['post'], url_path='credit-missed')
    def credit_missed(self, request, pk=None):
        affiliate = self.get_object()
        if affiliate.status != Affiliate.Status.ACTIVE:
            return Response({'detail': 'activate the agent first'}, status=status.HTTP_400_BAD_REQUEST)
        from . import netloss
        days = netloss.close_agent_days(affiliate.pk)
        credited = services.credit_missed_tickets(affiliate.pk)
        if days:
            services.pay_out_earnings(affiliate_id=affiliate.pk)
        accounts_services.audit(affiliate.player_id, 'affiliate_credit_missed', request, credited=credited, days=days)
        return Response({'credited': credited, 'days': days})

    @action(detail=True, methods=['post'], url_path='link-customer')
    def link_customer(self, request, pk=None):
        """Link a customer whose sign-up link was lost (or move them here).
        Body: {player: username / email / id, credit_from?: YYYY-MM-DD}."""
        player = accounts_services.find_player(str(request.data.get('player') or ''))
        if player is None:
            return Response({'detail': 'no player with that username, email or id'}, status=status.HTTP_400_BAD_REQUEST)
        raw = str(request.data.get('credit_from') or '').strip()
        credit_from = None
        if raw:
            try:
                credit_from = timezone.make_aware(datetime.combine(date.fromisoformat(raw), time.min))
            except ValueError:
                return Response({'detail': 'credit_from must be YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)
        previous = Referral.objects.filter(player_id=player.id).values_list('affiliate__code', flat=True).first()
        try:
            referral, credited = services.link_customer(int(pk), player.id, credit_from=credit_from,
                                                        linked_by=request.user.get_username())
        except services.AffiliateError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        accounts_services.audit(player.id, 'affiliate_customer_linked', request, agent=referral.affiliate.code,
                                previous_agent=previous or '', credit_from=referral.counts_from.isoformat(),
                                credited=credited)
        return Response({'player': player.username, 'previous_agent': previous, 'credited': credited,
                         'counts_from': referral.counts_from})

    @action(detail=True, methods=['get', 'post'], url_path='deposit-commissions')
    def deposit_commissions(self, request, pk=None):
        """GET: every customer the agent referred and their deposit commission
        (paid, waiting, due, or why not). POST {player_ids?: [...], override?: bool}:
        pay what's due — or, with override, the chosen customers without the rules."""
        affiliate = self.get_object()
        if request.method == 'GET':
            return Response(_money_json(services.cpa_audit(affiliate)))
        raw = request.data.get('player_ids') or []
        try:
            player_ids = [int(x) for x in raw] if isinstance(raw, list) else []
        except (TypeError, ValueError):
            return Response({'detail': 'player_ids must be a list of ids'}, status=status.HTTP_400_BAD_REQUEST)
        override = bool(request.data.get('override'))
        try:
            result = services.pay_cpa(affiliate.pk, player_ids=player_ids or None, override=override,
                                      by=request.user.get_username())
        except services.AffiliateError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        accounts_services.audit(affiliate.player_id, 'affiliate_cpa_paid_by_staff', request, override=override,
                                player_ids=player_ids, **result)
        if result['created'] or result['approved']:
            services.pay_out_earnings(affiliate_id=affiliate.pk)
        return Response(result)

    @action(detail=True, methods=['post'], url_path='terms')
    def terms(self, request, pk=None):
        fields = ('code', 'revshare_percent', 'cpa_amount', 'cpa_min_deposit', 'cpa_percent', 'cpa_cap', 'note')
        try:
            affiliate = services.update_terms(int(pk), **{f: request.data.get(f) for f in fields})
        except (services.AffiliateError, ArithmeticError, ValueError) as exc:
            return Response({'detail': str(exc) or 'invalid value'}, status=status.HTTP_400_BAD_REQUEST)
        accounts_services.audit(affiliate.player_id, 'affiliate_terms', request, **{
            f: str(getattr(affiliate, f)) for f in fields
        })
        return Response(self.get_serializer(self.get_queryset().get(pk=affiliate.pk)).data)


class AdminCommissionViewSet(mixins.ListModelMixin, viewsets.GenericViewSet):
    """Staff: commissions to review and pay."""
    serializer_class = CommissionSerializer
    permission_classes = [IsAdminUser]
    pagination_class = AffiliatePagination

    def get_queryset(self):
        qs = Commission.objects.select_related('affiliate').order_by('-created_at')
        params = self.request.query_params
        if params.get('status'):
            qs = qs.filter(status=params['status'])
        if params.get('affiliate'):
            qs = qs.filter(affiliate_id=params['affiliate'])
        q = (params.get('q') or '').strip()
        return qs.filter(affiliate__in=_affiliates_matching(q)) if q else qs

    @action(detail=True, methods=['post'], url_path='approve')
    def approve(self, request, pk=None):
        commission = services.approve(int(pk))
        accounts_services.audit(commission.affiliate.player_id, 'affiliate_commission_paid', request,
                                commission_id=commission.id, amount=str(commission.amount))
        return Response(self.get_serializer(commission).data)

    @action(detail=True, methods=['post'], url_path='reject')
    def reject(self, request, pk=None):
        try:
            commission = services.reject(int(pk), str(request.data.get('note') or ''))
        except services.AffiliateError as exc:
            return Response({'detail': str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response(self.get_serializer(commission).data)

    @action(detail=False, methods=['post'], url_path='run')
    def run(self, request):
        """Compute now: new CPAs and any losing tickets not yet credited (idempotent)."""
        today = request.data.get('today')
        try:
            result = services.run_commissions(today=date.fromisoformat(today) if today else None)
            result['tickets'] = services.credit_losing_tickets()
        except ValueError:
            return Response({'detail': 'today must be YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)


def _my_affiliate(request):
    player, denied = _player_or_403(request)
    if denied:
        return None, denied
    affiliate = services.get_for_player(player.id)
    if affiliate is None:
        return None, Response({'detail': 'not an affiliate'}, status=status.HTTP_404_NOT_FOUND)
    return affiliate, None


class MyCustomersView(APIView):
    """GET /api/affiliates/me/customers/?page=&page_size=&q= — every customer
    linked to the agent, newest first, one page at a time (names masked for
    the agent, in full for staff viewing as them)."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        affiliate, denied = _my_affiliate(request)
        if denied:
            return denied
        paginator = AffiliatePagination()
        qs = affiliate.referrals.order_by('-created_at')
        q = (request.query_params.get('q') or '').strip()
        if q:
            from apps.accounts.models import Player
            qs = qs.filter(player_id__in=Player.objects.filter(username__icontains=q).values('id'))
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(
            services.customer_rows(affiliate, page, mask=not impersonation.is_impersonated(request)))


class MyHistoryView(APIView):
    """GET /api/affiliates/me/history/?kind=commissions|payouts&page= — the
    agent's earnings or withdrawals, newest first, one page at a time."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        affiliate, denied = _my_affiliate(request)
        if denied:
            return denied
        paginator = AffiliatePagination()
        if request.query_params.get('kind') == 'payouts':
            page = paginator.paginate_queryset(affiliate.payouts.order_by('-created_at'), request, view=self)
            return paginator.get_paginated_response(PayoutSerializer(page, many=True).data)
        qs = affiliate.commissions.exclude(status=Commission.Status.REJECTED).order_by('-created_at')
        page = paginator.paginate_queryset(qs, request, view=self)
        return paginator.get_paginated_response(CommissionSerializer(page, many=True).data)
