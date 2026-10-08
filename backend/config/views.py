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
    """The operator dashboard: today's money, the queues that need a person,
    and the sportsbook's live state. Original keys are kept for older clients."""
    from datetime import timedelta
    from decimal import Decimal

    from django.db.models import Q, Sum
    from django.db.models.functions import TruncDate
    from django.utils import timezone

    from apps.accounts.models import KYCSubmission
    from apps.affiliates.models import Affiliate, Commission
    from apps.sportsbook.models import BetSlip, Event, Market
    from apps.sportsbook.services import LIVE_STATUSES
    from apps.wallet.models import LedgerEntry, PaymentTransaction

    now = timezone.now()
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)

    def total(qs):
        return qs.aggregate(v=Sum('amount'))['v'] or Decimal('0')

    today = LedgerEntry.objects.filter(created_at__gte=start)
    deposits = total(today.filter(kind='deposit'))
    withdrawals = -total(today.filter(kind='withdrawal'))
    stakes = -total(today.filter(kind__in=('bet_stake', 'casino_debit')))
    payouts = total(today.filter(kind__in=('bet_payout', 'casino_credit')))
    bonuses = total(today.filter(kind__in=('bonus', 'affiliate')))

    # Last 7 days of deposits and gross gaming revenue (stakes - payouts), for charts.
    week_start = start - timedelta(days=6)
    rows = (LedgerEntry.objects.filter(created_at__gte=week_start)
            .annotate(day=TruncDate('created_at')).values('day', 'kind').annotate(v=Sum('amount')))
    days = {(week_start + timedelta(days=i)).date(): {'deposits': Decimal('0'), 'ggr': Decimal('0')} for i in range(7)}
    for r in rows:
        d = days.get(r['day'])
        if d is None:
            continue
        if r['kind'] == 'deposit':
            d['deposits'] += r['v']
        elif r['kind'] in ('bet_stake', 'casino_debit', 'bet_payout', 'casino_credit'):
            d['ggr'] -= r['v']  # stakes are negative entries, payouts positive

    open_bets = Bet.objects.filter(status__in=('open', 'accepting')).count()
    open_slips = BetSlip.objects.filter(status__in=('open', 'accepting')).count()
    return Response({
        # legacy keys
        'online_players': Player.objects.count(),
        'open_bets': open_bets,
        'active_promotions': Promotion.objects.filter(active=True).count(),
        'open_chats': ChatMessage.objects.values('channel').distinct().count(),
        'today': {
            'deposits': str(deposits), 'withdrawals': str(withdrawals), 'stakes': str(stakes),
            'payouts': str(payouts), 'ggr': str(stakes - payouts), 'bonuses': str(bonuses),
            'new_players': Player.objects.filter(created_at__gte=start).count(),
        },
        'players': {
            'total': Player.objects.count(),
            'verified': Player.objects.filter(kyc_status=Player.Kyc.VERIFIED).count(),
            'suspended': Player.objects.filter(is_suspended=True).count(),
        },
        'queues': {
            'kyc_pending': KYCSubmission.objects.filter(status=KYCSubmission.Status.PENDING).count(),
            'payments_pending': PaymentTransaction.objects.filter(status=PaymentTransaction.Status.PENDING).count(),
            'affiliates_pending': Affiliate.objects.filter(status=Affiliate.Status.PENDING).count(),
            'commissions_pending': Commission.objects.filter(status=Commission.Status.PENDING).count(),
            'markets_to_settle': Market.objects.filter(settled=False).filter(
                Q(needs_review=True) | Q(kind=Market.Kind.MANUAL), event__starts_at__lt=now - timedelta(hours=2),
            ).count(),
        },
        'sportsbook': {
            'live': Event.objects.filter(status__in=LIVE_STATUSES).count(),
            'upcoming': Event.objects.filter(starts_at__gt=now, is_open=True, has_odds=True).count(),
            'unpriced': Event.objects.filter(starts_at__gt=now, has_odds=False).count(),
            'open_bets': open_bets, 'open_slips': open_slips,
        },
        'week': [{'day': d.isoformat(), 'deposits': str(v['deposits']), 'ggr': str(v['ggr'])} for d, v in days.items()],
    })
