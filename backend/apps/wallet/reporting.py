"""wallet reporting — read-only aggregations over the ledger for the analytics
screens (platform-wide, or scoped to a set of players such as an affiliate's
referrals). Every figure is derived from immutable ledger entries, so it is
exact and always current. Re-exported from wallet.services.

Sign conventions: stakes are negative entries and wins/refunds positive, so
  turnover (stakes) = -(bet_stake + casino_debit)
  wins paid          =   bet_payout + casino_credit
  GGR (player losses) = turnover - wins paid
  NGR                = GGR - bonuses
"""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Iterable, Optional

from django.db.models import Count, Min, Q, Sum
from django.db.models.functions import TruncDay, TruncHour, TruncMinute, TruncMonth

from common.timeframes import bucket_key

from .models import LedgerEntry

ZERO = Decimal('0')
SPORTS_STAKE, SPORTS_WIN = 'bet_stake', 'bet_payout'
CASINO_STAKE, CASINO_WIN = 'casino_debit', 'casino_credit'
STAKE_KINDS = (SPORTS_STAKE, CASINO_STAKE)
WIN_KINDS = (SPORTS_WIN, CASINO_WIN)
GAMING_KINDS = STAKE_KINDS + WIN_KINDS
ACTIVITY_KINDS = ('deposit', 'withdrawal', *GAMING_KINDS, 'bonus')
_TRUNC = {'minute': TruncMinute, 'hour': TruncHour, 'day': TruncDay, 'month': TruncMonth}


def _scope(player_ids: Optional[Iterable[int]], start: Optional[datetime], end: Optional[datetime]):
    qs = LedgerEntry.objects.all()
    if player_ids is not None:
        qs = qs.filter(wallet__player_id__in=list(player_ids))
    if start is not None:
        qs = qs.filter(created_at__gte=start)
    if end is not None:
        qs = qs.filter(created_at__lt=end)
    return qs


def _money(v) -> str:
    return str((v or ZERO).quantize(Decimal('0.01')))


def first_deposits(player_ids: Optional[Iterable[int]] = None) -> dict[int, datetime]:
    """When each player first deposited (players who never did are absent)."""
    qs = LedgerEntry.objects.filter(kind='deposit')
    if player_ids is not None:
        qs = qs.filter(wallet__player_id__in=list(player_ids))
    return {
        r['wallet__player_id']: r['first']
        for r in qs.values('wallet__player_id').annotate(first=Min('created_at'))
    }


def first_deposit_amounts(player_ids: Iterable[int]) -> dict[int, Decimal]:
    """The amount of each player's first deposit (never-deposited players absent)."""
    out: dict[int, Decimal] = {}
    rows = (LedgerEntry.objects.filter(kind='deposit', wallet__player_id__in=list(player_ids))
            .order_by('wallet__player_id', 'created_at', 'id').values_list('wallet__player_id', 'amount'))
    for pid, amount in rows:
        out.setdefault(pid, amount)
    return out


def deposit_count(player_id: int) -> int:
    return LedgerEntry.objects.filter(kind='deposit', wallet__player_id=player_id).count()


def _ftd_count(player_ids, start, end) -> int:
    firsts = first_deposits(player_ids)
    return sum(1 for t in firsts.values() if (start is None or t >= start) and t < end)


def ledger_kpis(player_ids: Optional[Iterable[int]], start: Optional[datetime], end: datetime) -> dict:
    """Money and activity KPIs for a window (player_ids=None: every player)."""
    ids = None if player_ids is None else list(player_ids)
    if ids is not None and not ids:
        return empty_kpis()
    qs = _scope(ids, start, end)
    by_kind = {r['kind']: r for r in qs.values('kind').annotate(total=Sum('amount'), n=Count('id'))}

    def total(kind):
        return (by_kind.get(kind) or {}).get('total') or ZERO

    def count(kind):
        return (by_kind.get(kind) or {}).get('n') or 0

    distinct = qs.aggregate(
        depositors=Count('wallet__player_id', filter=Q(kind='deposit'), distinct=True),
        active=Count('wallet__player_id', filter=Q(kind__in=GAMING_KINDS), distinct=True),
    )
    sports_stakes, casino_stakes = -total(SPORTS_STAKE), -total(CASINO_STAKE)
    sports_wins, casino_wins = total(SPORTS_WIN), total(CASINO_WIN)
    stakes, wins = sports_stakes + casino_stakes, sports_wins + casino_wins
    ggr = stakes - wins
    bonuses = total('bonus')
    deposits, withdrawals = total('deposit'), -total('withdrawal')
    return {
        'deposits': _money(deposits), 'deposit_count': count('deposit'),
        'withdrawals': _money(withdrawals), 'withdrawal_count': count('withdrawal'),
        'net_deposits': _money(deposits - withdrawals),
        'depositors': distinct['depositors'], 'ftds': _ftd_count(ids, start, end),
        'active_players': distinct['active'],
        'plays': count(SPORTS_STAKE) + count(CASINO_STAKE),
        'stakes': _money(stakes), 'wins': _money(wins),
        'ggr': _money(ggr), 'player_losses': _money(ggr),
        'bonuses': _money(bonuses), 'ngr': _money(ggr - bonuses),
        'margin_percent': f'{(ggr / stakes * 100):.2f}' if stakes > 0 else None,
        'avg_deposit': _money(deposits / count('deposit')) if count('deposit') else '0.00',
        'sportsbook': {
            'plays': count(SPORTS_STAKE), 'stakes': _money(sports_stakes), 'wins': _money(sports_wins),
            'ggr': _money(sports_stakes - sports_wins),
        },
        'casino': {
            'plays': count(CASINO_STAKE), 'stakes': _money(casino_stakes), 'wins': _money(casino_wins),
            'ggr': _money(casino_stakes - casino_wins),
        },
    }


def empty_kpis() -> dict:
    zero_product = {'plays': 0, 'stakes': '0.00', 'wins': '0.00', 'ggr': '0.00'}
    return {
        'deposits': '0.00', 'deposit_count': 0, 'withdrawals': '0.00', 'withdrawal_count': 0,
        'net_deposits': '0.00', 'depositors': 0, 'ftds': 0, 'active_players': 0, 'plays': 0,
        'stakes': '0.00', 'wins': '0.00', 'ggr': '0.00', 'player_losses': '0.00', 'bonuses': '0.00',
        'ngr': '0.00', 'margin_percent': None, 'avg_deposit': '0.00',
        'sportsbook': dict(zero_product), 'casino': dict(zero_product),
    }


def ledger_series(
    player_ids: Optional[Iterable[int]], start: Optional[datetime], end: datetime, bucket: str,
) -> dict[str, dict]:
    """Per-bucket deposits, withdrawals, stakes, wins, GGR, NGR and plays,
    keyed by the bucket's ISO start (see common.timeframes.bucket_key)."""
    ids = None if player_ids is None else list(player_ids)
    if ids is not None and not ids:
        return {}
    rows = (
        _scope(ids, start, end).filter(kind__in=ACTIVITY_KINDS)
        .annotate(b=_TRUNC[bucket]('created_at')).values('b', 'kind')
        .annotate(total=Sum('amount'), n=Count('id'))
    )
    out: dict[str, dict] = {}
    for r in rows:
        key = bucket_key(r['b'], bucket)
        d = out.setdefault(key, {'deposits': ZERO, 'withdrawals': ZERO, 'stakes': ZERO, 'wins': ZERO,
                                 'bonuses': ZERO, 'plays': 0})
        v = r['total'] or ZERO
        if r['kind'] == 'deposit':
            d['deposits'] += v
        elif r['kind'] == 'withdrawal':
            d['withdrawals'] -= v
        elif r['kind'] in STAKE_KINDS:
            d['stakes'] -= v
            d['plays'] += r['n']
        elif r['kind'] in WIN_KINDS:
            d['wins'] += v
        elif r['kind'] == 'bonus':
            d['bonuses'] += v
    return {
        k: {
            'deposits': _money(d['deposits']), 'withdrawals': _money(d['withdrawals']),
            'stakes': _money(d['stakes']), 'wins': _money(d['wins']),
            'ggr': _money(d['stakes'] - d['wins']), 'ngr': _money(d['stakes'] - d['wins'] - d['bonuses']),
            'plays': d['plays'],
        }
        for k, d in out.items()
    }


def player_breakdown(player_ids: Iterable[int], start: Optional[datetime], end: datetime) -> dict[int, dict]:
    """Per player in the window: deposits, stakes, wins, bonuses, plays, GGR, NGR."""
    ids = list(player_ids)
    if not ids:
        return {}
    rows = (_scope(ids, start, end).values('wallet__player_id', 'kind')
            .annotate(total=Sum('amount'), n=Count('id')))
    out: dict[int, dict] = {}
    for r in rows:
        d = out.setdefault(r['wallet__player_id'], {'deposits': ZERO, 'stakes': ZERO, 'wins': ZERO,
                                                     'bonuses': ZERO, 'plays': 0})
        v = r['total'] or ZERO
        if r['kind'] == 'deposit':
            d['deposits'] += v
        elif r['kind'] in STAKE_KINDS:
            d['stakes'] -= v
            d['plays'] += r['n']
        elif r['kind'] in WIN_KINDS:
            d['wins'] += v
        elif r['kind'] == 'bonus':
            d['bonuses'] += v
    for d in out.values():
        d['ggr'] = d['stakes'] - d['wins']
        d['ngr'] = d['ggr'] - d['bonuses']
    return out


def recent_activity(player_ids: Optional[Iterable[int]] = None, *, limit: int = 30) -> list[dict]:
    """The latest money movements (deposits, withdrawals, bets, wins, bonuses), newest first."""
    ids = None if player_ids is None else list(player_ids)
    if ids is not None and not ids:
        return []
    rows = (_scope(ids, None, None).filter(kind__in=ACTIVITY_KINDS)
            .order_by('-created_at', '-id').values('id', 'created_at', 'kind', 'amount', 'wallet__player_id')[:limit])
    return [
        {'id': r['id'], 'at': r['created_at'], 'kind': r['kind'], 'amount': _money(abs(r['amount'])),
         'player_id': r['wallet__player_id']}
        for r in rows
    ]


def earliest_entry(player_ids: Optional[Iterable[int]] = None) -> Optional[datetime]:
    ids = None if player_ids is None else list(player_ids)
    if ids is not None and not ids:
        return None
    return _scope(ids, None, None).aggregate(t=Min('created_at'))['t']
