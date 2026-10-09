"""affiliates transport — views move data; logic lives in services."""
from __future__ import annotations

from datetime import date

from django.db.models import Count
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts import services as accounts_services
from common.timeframes import TimeframeError

from . import services
from .models import Affiliate, Commission
from .serializers import AdminAffiliateSerializer, AffiliateSerializer, CommissionSerializer


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
        if affiliate.status == Affiliate.Status.ACTIVE:
            data['stats'] = services.dashboard(affiliate)
            data['commissions'] = CommissionSerializer(affiliate.commissions.all()[:50], many=True).data
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


class TermsView(APIView):
    """Public: the programme's default terms, for the join page."""
    permission_classes = [AllowAny]

    def get(self, request):
        from django.conf import settings
        return Response({
            'revshare_percent': str(getattr(settings, 'AFFILIATE_DEFAULT_REVSHARE', 25)),
            'cpa_amount': str(getattr(settings, 'AFFILIATE_DEFAULT_CPA', 0)),
            'cpa_min_deposit': str(getattr(settings, 'AFFILIATE_DEFAULT_CPA_MIN_DEPOSIT', 20)),
        })


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

    def get_queryset(self):
        qs = Affiliate.objects.annotate(
            referrals_count=Count('referrals', distinct=True), clicks_count=Count('clicks', distinct=True),
        ).order_by('-created_at')
        wanted = self.request.query_params.get('status')
        return qs.filter(status=wanted) if wanted else qs

    def get_serializer_context(self):
        ctx = super().get_serializer_context()
        ids = list(Affiliate.objects.values_list('player_id', flat=True))
        ctx['usernames'] = accounts_services.usernames_for(ids)
        return ctx

    def retrieve(self, request, *args, **kwargs):
        affiliate = self.get_object()
        data = self.get_serializer(affiliate).data
        data['stats'] = services.dashboard(affiliate)
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

    @action(detail=True, methods=['post'], url_path='terms')
    def terms(self, request, pk=None):
        fields = ('code', 'revshare_percent', 'cpa_amount', 'cpa_min_deposit', 'note')
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

    def get_queryset(self):
        qs = Commission.objects.select_related('affiliate').order_by('-created_at')
        params = self.request.query_params
        if params.get('status'):
            qs = qs.filter(status=params['status'])
        if params.get('affiliate'):
            qs = qs.filter(affiliate_id=params['affiliate'])
        return qs

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
        """Compute now: last month's revenue share and new CPAs (idempotent).
        Optional {today: 'YYYY-MM-DD'} to close a different month."""
        today = request.data.get('today')
        try:
            result = services.run_commissions(today=date.fromisoformat(today) if today else None)
        except ValueError:
            return Response({'detail': 'today must be YYYY-MM-DD'}, status=status.HTTP_400_BAD_REQUEST)
        return Response(result)
