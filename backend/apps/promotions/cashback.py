"""Cashback: a share of a period's losses back, by rules the operator sets.

Every CashbackSettings.period_days days (counted from `starts_on`), each player's
real-money results for the period are added up (Deposit and Winnings wallets,
sports and Aviator: stakes minus winnings; Bonus-wallet play doesn't count):

    loss         stakes - winnings in the period (only a positive loss qualifies)
    tickets      sports tickets placed with real money in the period
    active days  days in the period with at least one real-money bet

The best active CashbackTier they meet (highest %) pays percent × loss, up to
the tier's max, to the Winnings wallet. Once per player per period (a unique
payout row and an idempotent ledger entry), run daily by a Celery beat job,
which also catches up on any period it missed. Suspended accounts are skipped.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time, timedelta
from decimal import ROUND_DOWN, Decimal

from django.db import IntegrityError, transaction
from django.db.models import Count, Sum
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import CashbackPayout, CashbackSettings, CashbackTier

logger = logging.getLogger(__name__)
CENT = Decimal('0.01')
GAMING = ('bet_stake', 'bet_payout', 'casino_debit', 'casino_credit', 'bet_reversal')
STAKES = ('bet_stake', 'casino_debit')
REAL = ('deposit', 'winnings')
MAX_CATCH_UP = 4


def _bounds(start: date, end: date) -> tuple[datetime, datetime]:
    tz = timezone.get_current_timezone()
    return timezone.make_aware(datetime.combine(start, time.min), tz), timezone.make_aware(datetime.combine(end, time.min), tz)


def period_stats(start: date, end: date) -> dict[int, dict]:
    """{player: {loss, tickets, active_days}} for players who bet real money in [start, end)."""
    from apps.sportsbook.models import Bet, BetSlip
    from apps.wallet.models import LedgerEntry
    lo, hi = _bounds(start, end)
    entries = LedgerEntry.objects.filter(created_at__gte=lo, created_at__lt=hi, bucket__in=REAL)
    stats: dict[int, dict] = {}
    for r in entries.filter(kind__in=GAMING).values('wallet__player_id').annotate(net=Sum('amount')):
        stats[r['wallet__player_id']] = {'loss': -(r['net'] or Decimal('0')), 'tickets': 0, 'active_days': 0}
    days = (entries.filter(kind__in=STAKES).annotate(day=TruncDate('created_at', tzinfo=timezone.get_current_timezone()))
            .values('wallet__player_id').annotate(n=Count('day', distinct=True)))
    for r in days:
        if r['wallet__player_id'] in stats:
            stats[r['wallet__player_id']]['active_days'] = r['n']
    for model in (Bet, BetSlip):
        rows = (model.objects.filter(placed_at__gte=lo, placed_at__lt=hi, player_id__in=list(stats))
                .exclude(wallet='bonus').exclude(status__in=('rejected', 'pending'))
                .values('player_id').annotate(n=Count('id')))
        for r in rows:
            stats[r['player_id']]['tickets'] += r['n']
    return stats


def best_tier(s: dict, tiers: list[CashbackTier]):
    for t in sorted(tiers, key=lambda t: (-t.percent, -t.min_loss)):
        if s['loss'] >= t.min_loss and s['tickets'] >= t.min_tickets and s['active_days'] >= t.min_active_days:
            return t
    return None


def amount_for(loss: Decimal, tier: CashbackTier) -> Decimal:
    amount = (loss * tier.percent / Decimal('100')).quantize(CENT, rounding=ROUND_DOWN)
    return min(amount, tier.max_amount) if tier.max_amount is not None else amount


def pay_period(start: date, end: date) -> dict:
    """Pay every qualifying player for [start, end). Safe to run again."""
    from apps.accounts.models import Player
    from apps.notifications import services as notes
    from apps.wallet import services as wallet
    tiers = list(CashbackTier.objects.filter(active=True))
    report = {'period': f'{start}..{end}', 'players': 0, 'paid': 0, 'total': Decimal('0')}
    if not tiers:
        return report
    stats = period_stats(start, end)
    report['players'] = len(stats)
    suspended = set(Player.objects.filter(pk__in=list(stats), is_suspended=True).values_list('pk', flat=True))
    for pid, s in stats.items():
        if pid in suspended or s['loss'] <= 0:
            continue
        tier = best_tier(s, tiers)
        if tier is None:
            continue
        amount = amount_for(s['loss'], tier)
        if amount < CENT:
            continue
        try:
            with transaction.atomic():
                CashbackPayout.objects.create(player_id=pid, period_start=start, period_end=end, loss=s['loss'],
                                              tickets=s['tickets'], active_days=s['active_days'], tier=tier,
                                              percent=tier.percent, amount=amount)
                wallet.credit(player_id=pid, amount=amount, kind='cashback', bucket='winnings',
                              idempotency_key=f'cashback:{pid}:{start}', reference=f'cashback:{start}')
        except IntegrityError:
            continue                                     # already paid for this period
        notes.notify(player_id=pid, kind='bonus_credited', title='Cashback paid',
                     body=f'${amount:.2f} cashback ({tier.percent.normalize():f}% of your losses '
                          f'{start:%d %b}–{end - timedelta(days=1):%d %b}) is in your Winnings.')
        report['paid'] += 1
        report['total'] += amount
    return report


def due_periods(cfg: CashbackSettings, today: date) -> list[tuple[date, date]]:
    """Finished periods not paid yet (oldest first, at most MAX_CATCH_UP)."""
    if not cfg.starts_on or cfg.period_days < 1:
        return []
    step = timedelta(days=cfg.period_days)
    start = cfg.last_period_start + step if cfg.last_period_start else cfg.starts_on
    out = []
    while start + step <= today and len(out) < MAX_CATCH_UP:
        out.append((start, start + step))
        start += step
    return out


def run(today: date | None = None) -> list[dict]:
    """The daily job: pay every finished, unpaid period."""
    cfg = CashbackSettings.load()
    if not cfg.enabled:
        return []
    today = today or timezone.localdate()
    reports = []
    for start, end in due_periods(cfg, today):
        reports.append(pay_period(start, end))
        CashbackSettings.objects.filter(pk=cfg.pk).update(last_period_start=start)
        logger.info('cashback %s', reports[-1])
    return reports
