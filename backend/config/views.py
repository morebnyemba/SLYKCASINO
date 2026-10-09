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
    from apps.affiliates.models import Affiliate, Commission, Payout
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
            'payouts_pending': Payout.objects.filter(status=Payout.Status.REQUESTED).count(),
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


@api_view(['GET'])
@permission_classes([IsAdminUser])
def admin_analytics(request):
    """GET /api/admin/analytics/?frame=…[&start=&end=] — platform analytics for
    any timeframe (live hour … all time, or a custom range): money and play
    KPIs, the sportsbook / casino split, signups and first deposits, a chart
    series, top affiliates, and what is happening right now. Polled by the
    admin for a live view; every figure comes straight from the ledger."""
    from collections import defaultdict
    from datetime import timedelta

    from django.utils import timezone

    from apps.accounts import services as accounts_services
    from apps.affiliates import services as affiliate_services
    from apps.affiliates.models import Referral
    from apps.jet.models import JetBet, JetRound
    from apps.sportsbook.models import BetSlip, Event
    from apps.sportsbook.services import LIVE_STATUSES
    from apps.wallet import services as wallet_services
    from common import timeframes

    q = request.query_params
    now = timezone.now()
    earliest = min(
        [t for t in (wallet_services.earliest_entry(), accounts_services.first_signup_at()) if t is not None],
        default=None,
    )
    try:
        window = timeframes.resolve(q.get('frame') or 'today', start=q.get('start'), end=q.get('end'),
                                    now=now, earliest=earliest)
    except timeframes.TimeframeError as exc:
        return Response({'detail': str(exc)}, status=400)
    s, e = window.start, window.end

    kpis = wallet_services.ledger_kpis(None, s, e)
    signup_times = accounts_services.signup_times(start=s, end=e)
    kpis['signups'] = len(signup_times)
    kpis['ftd_rate'] = f"{kpis['ftds'] / len(signup_times) * 100:.1f}" if signup_times else None
    referred = list(Referral.objects.values_list('player_id', flat=True))
    aff = wallet_services.ledger_kpis(referred, s, e) if referred else wallet_services.empty_kpis()
    kpis['affiliate'] = {
        'deposits': aff['deposits'], 'ngr': aff['ngr'], 'active_players': aff['active_players'],
        'signups': Referral.objects.filter(created_at__lt=e, **({'created_at__gte': s} if s else {})).count(),
    }

    series = wallet_services.ledger_series(None, s, e, window.bucket)
    joins: dict[str, int] = defaultdict(int)
    for t in signup_times:
        joins[timeframes.bucket_key(t, window.bucket)] += 1
    firsts = wallet_services.first_deposits()
    ftds: dict[str, int] = defaultdict(int)
    for t in firsts.values():
        if (s is None or t >= s) and t < e:
            ftds[timeframes.bucket_key(t, window.bucket)] += 1
    keys = [timeframes.bucket_key(b, window.bucket) for b in timeframes.bucket_starts(window)] or sorted(series)
    empty = {'deposits': '0.00', 'withdrawals': '0.00', 'stakes': '0.00', 'wins': '0.00', 'ggr': '0.00',
             'ngr': '0.00', 'plays': 0}
    points = [{'t': k, **(series.get(k) or empty), 'signups': joins.get(k, 0), 'ftds': ftds.get(k, 0)} for k in keys]

    activity = wallet_services.recent_activity(limit=30)
    names = accounts_services.usernames_for([a['player_id'] for a in activity])
    for a in activity:
        a['player'] = names.get(a.pop('player_id'), '?')

    hour = wallet_services.ledger_kpis(None, now - timedelta(hours=1), now)
    rnd = JetRound.objects.order_by('-id').first()
    right_now = {
        'last_hour': {k: hour[k] for k in ('deposits', 'plays', 'stakes', 'ggr', 'active_players')},
        'live_matches': Event.objects.filter(status__in=LIVE_STATUSES).count(),
        'open_bets': Bet.objects.filter(status__in=('open', 'accepting')).count()
        + BetSlip.objects.filter(status__in=('open', 'accepting')).count(),
        'aviator': {
            'round': rnd.id if rnd else None, 'status': rnd.status if rnd else None,
            'players': JetBet.objects.filter(round=rnd).count() if rnd else 0,
        },
        'signups_last_hour': len(accounts_services.signup_times(start=now - timedelta(hours=1), end=now)),
    }
    return Response({
        'frame': window.frame, 'label': window.label, 'bucket': window.bucket,
        'start': window.start, 'end': window.end, 'generated_at': now,
        'kpis': kpis, 'series': points, 'activity': activity, 'right_now': right_now,
        'top_affiliates': affiliate_services.top_affiliates(s, e),
    })
