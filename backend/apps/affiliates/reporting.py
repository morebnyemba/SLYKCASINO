"""affiliates analytics — live KPIs for one affiliate (or every affiliate, for
operators) over any timeframe, from clicks and referrals here and the wallet
ledger of the referred players. Read-only; re-exported from services.

Player money counts for every referred player, whenever they signed up, so a
window shows what the affiliate's players did in that window.
"""
from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import Optional

from django.db.models import Sum

from apps.accounts import services as accounts_services
from apps.wallet import services as wallet_services
from common import timeframes

from . import utils
from .models import Affiliate, Commission, Referral

ZERO = Decimal('0')


def _money(v) -> str:
    return str((v or ZERO).quantize(Decimal('0.01')))


def _rate(part: int, whole: int) -> Optional[str]:
    return f'{part / whole * 100:.1f}' if whole else None


def _in(moment, start, end) -> bool:
    return (start is None or moment >= start) and moment < end


def affiliate_analytics(
    affiliate: Affiliate, frame: str = 'today', *, start: Optional[str] = None, end: Optional[str] = None,
    now=None,
) -> dict:
    """Everything the affiliate dashboard shows for one timeframe."""
    referrals = list(affiliate.referrals.values('player_id', 'campaign', 'created_at'))
    ids = [r['player_id'] for r in referrals]
    window = timeframes.resolve(frame, start=start, end=end, now=now, earliest=affiliate.created_at)
    s, e = window.start, window.end

    kpis = wallet_services.ledger_kpis(ids, s, e)
    clicks_qs = affiliate.clicks.all()
    if s is not None:
        clicks_qs = clicks_qs.filter(created_at__gte=s)
    clicks_qs = clicks_qs.filter(created_at__lt=e)
    clicks = list(clicks_qs.values_list('created_at', 'campaign'))
    signups = [r for r in referrals if _in(r['created_at'], s, e)]
    firsts = wallet_services.first_deposits(ids)
    ftd_ids = {pid for pid, t in firsts.items() if _in(t, s, e)}

    ngr = Decimal(kpis['ngr'])
    earned = affiliate.commissions.exclude(status=Commission.Status.REJECTED)
    cpa_qs = earned.filter(kind=Commission.Kind.CPA, created_at__lt=e)
    if s is not None:
        cpa_qs = cpa_qs.filter(created_at__gte=s)
    paid_qs = affiliate.commissions.filter(status=Commission.Status.PAID, paid_at__lt=e)
    if s is not None:
        paid_qs = paid_qs.filter(paid_at__gte=s)

    kpis.update({
        'clicks': len(clicks),
        'signups': len(signups),
        'ftds': len(ftd_ids),
        'signup_rate': _rate(len(signups), len(clicks)),
        'ftd_rate': _rate(len(ftd_ids), len(signups)) if signups else None,
        'referrals_total': len(ids),
        'revshare_percent': str(affiliate.revshare_percent),
        'revshare_estimate': _money(utils.commission_for(ngr, affiliate.revshare_percent)),
        'cpa_earned': _money(cpa_qs.aggregate(v=Sum('amount'))['v']),
        'commission_paid': _money(paid_qs.aggregate(v=Sum('amount'))['v']),
    })
    kpis['commission_estimate'] = _money(Decimal(kpis['revshare_estimate']) + Decimal(kpis['cpa_earned']))

    # Chart: money per bucket plus clicks, signups and first deposits.
    series = wallet_services.ledger_series(ids, s, e, window.bucket)
    extra: dict[str, dict] = defaultdict(lambda: {'clicks': 0, 'signups': 0, 'ftds': 0})
    for t, _ in clicks:
        extra[timeframes.bucket_key(t, window.bucket)]['clicks'] += 1
    for r in signups:
        extra[timeframes.bucket_key(r['created_at'], window.bucket)]['signups'] += 1
    for pid in ftd_ids:
        extra[timeframes.bucket_key(firsts[pid], window.bucket)]['ftds'] += 1
    points = _points(window, series, extra)

    # Campaigns and players.
    per_player = wallet_services.player_breakdown(ids, s, e)
    campaign_of = {r['player_id']: r['campaign'] or '' for r in referrals}
    camps: dict[str, dict] = defaultdict(lambda: {
        'clicks': 0, 'signups': 0, 'ftds': 0, 'deposits': ZERO, 'stakes': ZERO, 'ngr': ZERO, 'plays': 0,
    })
    for _, c in clicks:
        camps[c or '']['clicks'] += 1
    for r in signups:
        camps[r['campaign'] or '']['signups'] += 1
    for pid in ftd_ids:
        camps[campaign_of.get(pid, '')]['ftds'] += 1
    for pid, d in per_player.items():
        c = camps[campaign_of.get(pid, '')]
        c['deposits'] += d['deposits']; c['stakes'] += d['stakes']; c['ngr'] += d['ngr']; c['plays'] += d['plays']
    campaigns = sorted(
        ({'campaign': name or '(no campaign)', **{k: (_money(v) if isinstance(v, Decimal) else v) for k, v in c.items()}}
         for name, c in camps.items()),
        key=lambda c: (-Decimal(c['ngr']), -c['clicks']),
    )

    names = accounts_services.usernames_for(list(per_player) + [r['player_id'] for r in signups[:20]])
    top = sorted(per_player.items(), key=lambda kv: (-kv[1]['ngr'], -kv[1]['stakes']))[:15]
    players = [
        {
            'player': utils.mask_username(names.get(pid, '?')), 'campaign': campaign_of.get(pid, ''),
            'deposits': _money(d['deposits']), 'stakes': _money(d['stakes']), 'wins': _money(d['wins']),
            'plays': d['plays'], 'ngr': _money(d['ngr']), 'first_deposit': pid in ftd_ids,
        }
        for pid, d in top
    ]

    activity = wallet_services.recent_activity(ids, limit=25)
    activity_names = accounts_services.usernames_for([a['player_id'] for a in activity])
    feed = [
        {'id': f"l{a['id']}", 'at': a['at'], 'kind': a['kind'], 'amount': a['amount'],
         'player': utils.mask_username(activity_names.get(a['player_id'], '?'))}
        for a in activity
    ]
    latest_signups = sorted(referrals, key=lambda r: r['created_at'], reverse=True)[:10]
    signup_names = accounts_services.usernames_for([r['player_id'] for r in latest_signups])
    feed += [
        {'id': f"s{r['player_id']}", 'at': r['created_at'], 'kind': 'signup', 'amount': None,
         'player': utils.mask_username(signup_names.get(r['player_id'], '?'))}
        for r in latest_signups
    ]
    feed.sort(key=lambda x: x['at'], reverse=True)

    return {
        'frame': window.frame, 'label': window.label, 'bucket': window.bucket,
        'start': window.start, 'end': window.end, 'generated_at': window.end,
        'kpis': kpis, 'series': points, 'campaigns': campaigns, 'players': players, 'activity': feed[:25],
    }


def _points(window, series: dict[str, dict], extra: dict[str, dict]) -> list[dict]:
    keys = [timeframes.bucket_key(b, window.bucket) for b in timeframes.bucket_starts(window)]
    if not keys:
        keys = sorted(set(series) | set(extra))
    empty = {'deposits': '0.00', 'withdrawals': '0.00', 'stakes': '0.00', 'wins': '0.00', 'ggr': '0.00',
             'ngr': '0.00', 'plays': 0}
    return [{'t': k, **(series.get(k) or empty), **(extra.get(k) or {'clicks': 0, 'signups': 0, 'ftds': 0})}
            for k in keys]


def top_affiliates(start, end, *, limit: int = 10) -> list[dict]:
    """Operator view: affiliates ranked by their players' NGR in the window."""
    rows = list(Referral.objects.values_list('affiliate_id', 'player_id'))
    if not rows:
        return []
    per_player = wallet_services.player_breakdown([pid for _, pid in rows], start, end)
    agg: dict[int, dict] = defaultdict(lambda: {'players': 0, 'deposits': ZERO, 'stakes': ZERO, 'ngr': ZERO, 'plays': 0})
    for aff_id, pid in rows:
        d = per_player.get(pid)
        if not d:
            continue
        a = agg[aff_id]
        a['players'] += 1
        a['deposits'] += d['deposits']; a['stakes'] += d['stakes']; a['ngr'] += d['ngr']; a['plays'] += d['plays']
    ranked = sorted(agg.items(), key=lambda kv: (-kv[1]['ngr'], -kv[1]['deposits']))[:limit]
    affiliates = {a.id: a for a in Affiliate.objects.filter(pk__in=[k for k, _ in ranked])}
    names = accounts_services.usernames_for([a.player_id for a in affiliates.values()])
    return [
        {
            'id': aff_id, 'code': affiliates[aff_id].code, 'owner': names.get(affiliates[aff_id].player_id, '?'),
            'active_players': a['players'], 'plays': a['plays'],
            'deposits': _money(a['deposits']), 'stakes': _money(a['stakes']), 'ngr': _money(a['ngr']),
        }
        for aff_id, a in ranked if aff_id in affiliates
    ]
