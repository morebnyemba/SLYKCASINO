"""Agent commission on customers' net loss — what they actually lose, not what
they stake on losing bets.

For each agent and each completed day (local time), from the moment the
programme switched to this (`net_loss_since`):

    net loss = real-money stakes − real-money winnings − bonus money turned into Winnings
               (every game: sports, Aviator, casino; Bonus-wallet play never counts)
             − stakes still riding at the end of the day + those riding at its start
               (a stake counts once its bet settles, so open bets at midnight can't be cashed in)
             + winnings of the agent's own account and of accounts sharing a payment
               number with the agent or a customer (their losses earn nothing)

pooled over all the agent's customers, with an earlier losing balance netted off
(carry-forward). The agent earns their % of what's left. Why this can't be
gamed: commission is a share (< 100%) of money the house actually kept from the
agent's pool, so an agent playing through fake customers always loses more than
they earn; hedging both sides through two customers nets out inside the pool;
hedging through their own or a payment-linked account is subtracted.

Days close in order (the carry needs it), hourly and on demand; each is closed
once (unique per agent and day). A day's commission above
`net_loss_review_above` waits for staff approval.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Iterable, Optional

from django.db import IntegrityError, transaction
from django.db.models import Q, Sum
from django.utils import timezone

from . import utils
from .models import Affiliate, AffiliateProgramme, Commission, NetLossDay, Referral

ZERO = Decimal('0.00')
CASH_STAKES = ('bet_stake', 'casino_debit')
CASH_WINS = ('bet_payout', 'casino_credit', 'bet_reversal')   # a reversal is negative: winnings taken back
MAX_DAYS_PER_RUN = 62
HEARTBEAT_KEY = 'affiliates:net-loss:last-close'


def _aware(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min))


@dataclass
class Money:
    stakes: Decimal = ZERO
    wins: Decimal = ZERO
    conversions: Decimal = ZERO
    open_in: Decimal = ZERO
    open_out: Decimal = ZERO

    @property
    def net(self) -> Decimal:
        return self.stakes - self.wins - self.conversions - self.open_out + self.open_in

    def add(self, other: 'Money') -> None:
        self.stakes += other.stakes
        self.wins += other.wins
        self.conversions += other.conversions
        self.open_in += other.open_in
        self.open_out += other.open_out


# -- the money -------------------------------------------------------------------

def ledger_money(player_ids: Iterable[int], start: datetime, end: datetime) -> dict[int, Money]:
    """Each player's real-money stakes, winnings and bonus conversions in [start, end)."""
    from apps.wallet.models import Bucket, LedgerEntry

    ids = list(player_ids)
    out: dict[int, Money] = defaultdict(Money)
    if not ids or start >= end:
        return out
    cash = (Bucket.DEPOSIT, Bucket.WINNINGS)
    rows = (LedgerEntry.objects.filter(wallet__player_id__in=ids, created_at__gte=start, created_at__lt=end)
            .filter(Q(kind__in=CASH_STAKES + CASH_WINS, bucket__in=cash) | Q(kind='bonus_conversion', bucket=Bucket.WINNINGS))
            .values('wallet__player_id', 'kind').annotate(total=Sum('amount')))
    for row in rows:
        m, total = out[row['wallet__player_id']], row['total'] or ZERO
        if row['kind'] in CASH_STAKES:
            m.stakes += -total
        elif row['kind'] == 'bonus_conversion':
            m.conversions += total
        else:
            m.wins += total
    return out


def open_stakes(player_ids: Iterable[int], at: datetime) -> dict[int, Decimal]:
    """Real-money stakes these players had riding at `at`: sports tickets, Aviator
    bets and casino rounds placed before it and settled after it (or not yet)."""
    from apps.casino.models import GameRound
    from apps.jet.models import JetBet
    from apps.sportsbook.models import Bet, BetSlip

    ids = list(player_ids)
    out: dict[int, Decimal] = defaultdict(lambda: ZERO)
    if not ids:
        return out
    riding = Q(settled_at__gte=at) | Q(settled_at__isnull=True)
    for model in (Bet, BetSlip):
        qs = (model.objects.filter(riding, player_id__in=ids, placed_at__lt=at)
              .exclude(wallet='bonus').exclude(status='pending')
              .filter(Q(settled_at__isnull=False) | Q(status__in=('accepting', 'open'))))
        for pid, stake, cashed, cashed_at in qs.values_list('player_id', 'stake', 'stake_cashed_out', 'cashed_out_at'):
            # A partial cash-out after `at` took that part of the stake off later.
            out[pid] += stake + (cashed if cashed_at and cashed_at >= at else ZERO)
    jet = (JetBet.objects.filter(riding, player_id__in=ids, created_at__lt=at, is_free=False).exclude(wallet='bonus')
           .filter(Q(settled_at__isnull=False) | Q(status='active')))
    for pid, stake in jet.values_list('player_id', 'stake'):
        out[pid] += stake
    rounds = (GameRound.objects.filter(riding, player_id__in=ids, created_at__lt=at, debit_confirmed=True)
              .exclude(wallet='bonus').filter(Q(settled_at__isnull=False) | Q(status='pending')))
    for pid, stake in rounds.values_list('player_id', 'stake'):
        out[pid] += stake
    return out


def window_money(windows: dict[int, tuple[datetime, datetime]]) -> dict[int, Money]:
    """Money per player over each player's own [start, end) window."""
    by_window: dict[tuple[datetime, datetime], list[int]] = defaultdict(list)
    for pid, w in windows.items():
        if w[0] < w[1]:
            by_window[w].append(pid)
    out: dict[int, Money] = {}
    for (start, end), ids in by_window.items():
        money = ledger_money(ids, start, end)
        opened, closed = open_stakes(ids, start), open_stakes(ids, end)
        for pid in ids:
            m = money.get(pid) or Money()
            m.open_in, m.open_out = opened[pid], closed[pid]
            out[pid] = m
    return out


def linked_outsiders(affiliate: Affiliate, customer_ids: Iterable[int]) -> set[int]:
    """Accounts sharing a deposit or payout number with the agent or any of
    their customers, other than the pool itself — where a hedge would hide."""
    from apps.risk import linking

    pool = set(customer_ids) | {affiliate.player_id}
    found: set[int] = set()
    for pid in pool:
        try:
            found |= linking.strongly_linked(pid)
        except Exception:  # noqa: BLE001 — linking is best-effort; never block a close
            continue
    return found - pool


# -- one day -----------------------------------------------------------------------

@dataclass
class DayResult:
    customers: int = 0
    pool: Money = field(default_factory=Money)
    hedge: Decimal = ZERO

    @property
    def net_loss(self) -> Decimal:
        return self.pool.net + self.hedge


def day_result(affiliate: Affiliate, start: datetime, end: datetime, *, programme: AffiliateProgramme,
               outsiders: Optional[set[int]] = None) -> DayResult:
    """The agent's pool over [start, end): customers from when they were linked."""
    links = list(affiliate.referrals.values_list('player_id', 'created_at', 'credit_from'))
    windows = {}
    for pid, created, credit_from in links:
        begins = max(start, credit_from or created)
        if begins < end:
            windows[pid] = (begins, end)
    result = DayResult(customers=len(windows))
    for m in window_money(windows).values():
        result.pool.add(m)
    others = {affiliate.player_id} | (outsiders if outsiders is not None else linked_outsiders(affiliate, windows))
    others -= set(windows)
    for m in window_money({pid: (start, end) for pid in others}).values():
        result.hedge += min(m.net, ZERO)        # their winnings count against the pool; their losses earn nothing
    return result


def _bounds(affiliate: Affiliate, day: date, programme: AffiliateProgramme) -> tuple[datetime, datetime]:
    start, end = _aware(day), _aware(day + timedelta(days=1))
    for floor in (programme.net_loss_since, affiliate.active_since):
        if floor and floor > start:
            start = floor
    return start, end


def _first_open_day(affiliate: Affiliate, programme: AffiliateProgramme) -> Optional[date]:
    last = affiliate.net_loss_days.order_by('-day').values_list('day', flat=True).first()
    if last:
        return last + timedelta(days=1)
    floors = [f for f in (programme.net_loss_since, affiliate.active_since or affiliate.approved_at) if f]
    if not programme.net_loss_since:
        return None
    return timezone.localdate(max(floors))


def close_agent_days(affiliate_id: int, *, today: Optional[date] = None, programme=None) -> int:
    """Close each completed day of one active agent not yet closed, oldest first."""
    programme = programme or AffiliateProgramme.load()
    today = today or timezone.localdate()
    closed = 0
    with transaction.atomic():
        affiliate = Affiliate.objects.select_for_update().filter(pk=affiliate_id, status=Affiliate.Status.ACTIVE).first()
        if affiliate is None:
            return 0
        day = _first_open_day(affiliate, programme)
        if day is None or day >= today:
            return 0
        last = affiliate.net_loss_days.order_by('-day').first()
        carried = last.carry_out if last else ZERO
        outsiders = linked_outsiders(affiliate, affiliate.referrals.values_list('player_id', flat=True))
        while day < today and closed < MAX_DAYS_PER_RUN:
            start, end = _bounds(affiliate, day, programme)
            result = day_result(affiliate, start, end, programme=programme, outsiders=outsiders)
            base, carry_out = utils.carry(result.net_loss, carried, programme.negative_carryover)
            amount = utils.commission_for(base, affiliate.revshare_percent)
            commission = None
            if amount > 0:
                review = programme.net_loss_review_above
                commission = Commission.objects.create(
                    affiliate=affiliate, kind=Commission.Kind.NET_LOSS, period=day, base_amount=base,
                    rate=affiliate.revshare_percent, amount=amount, active_players=result.customers,
                    status=(Commission.Status.PENDING if review and amount > review else Commission.Status.APPROVED),
                    decided_at=timezone.now(),
                )
            NetLossDay.objects.create(
                affiliate=affiliate, day=day, customers=result.customers, stakes=result.pool.stakes,
                wins=result.pool.wins, bonus_conversions=result.pool.conversions, open_in=result.pool.open_in,
                open_out=result.pool.open_out, hedge=result.hedge, net_loss=result.net_loss, carried_in=carried,
                carry_out=carry_out, rate=affiliate.revshare_percent, commission=commission,
            )
            carried = carry_out
            closed += 1
            day += timedelta(days=1)
    return closed


def close_days(*, today: Optional[date] = None) -> int:
    """Hourly: close every active agent's completed days. Idempotent."""
    from . import services

    programme = AffiliateProgramme.load()
    closed = 0
    for aid in Affiliate.objects.filter(status=Affiliate.Status.ACTIVE).values_list('pk', flat=True):
        try:
            closed += close_agent_days(aid, today=today, programme=programme)
        except IntegrityError:
            continue   # closed by an overlapping run
        except Exception:  # noqa: BLE001 — one agent must never stop the rest
            import logging
            logging.getLogger(__name__).exception('closing net-loss days failed for agent %s', aid)
    _heartbeat()
    if closed:
        services.pay_out_earnings()
    return closed


def _heartbeat() -> None:
    from django.core.cache import cache
    try:
        cache.set(HEARTBEAT_KEY, timezone.now().isoformat(), timeout=None)
    except Exception:  # noqa: BLE001
        pass


def last_close() -> Optional[datetime]:
    from django.core.cache import cache
    from django.utils.dateparse import parse_datetime
    try:
        raw = cache.get(HEARTBEAT_KEY)
    except Exception:  # noqa: BLE001
        return None
    return parse_datetime(raw) if raw else None


def days_behind(*, today: Optional[date] = None) -> dict:
    """Active agents with completed days not yet closed (the job is behind)."""
    programme = AffiliateProgramme.load()
    today = today or timezone.localdate()
    agents, days = 0, 0
    for affiliate in Affiliate.objects.filter(status=Affiliate.Status.ACTIVE):
        first = _first_open_day(affiliate, programme)
        if first and first < today:
            agents += 1
            days += (today - first).days
    return {'agents': agents, 'days': days}


def today_estimate(affiliate: Affiliate, *, now: Optional[datetime] = None) -> dict:
    """Live: the pool so far today and the commission it would pay if the day
    closed now (the real figure is fixed after midnight)."""
    programme = AffiliateProgramme.load()
    now = now or timezone.now()
    today = timezone.localdate(now)
    if not programme.net_loss_since:
        return {'net_loss': ZERO, 'commission': ZERO, 'carried_in': ZERO, 'customers': 0}
    start, _ = _bounds(affiliate, today, programme)
    result = day_result(affiliate, min(start, now), now, programme=programme, outsiders=set())
    last = affiliate.net_loss_days.order_by('-day').first()
    carried = last.carry_out if last else ZERO
    base, _ = utils.carry(result.net_loss, carried, programme.negative_carryover)
    return {'net_loss': result.net_loss.quantize(Decimal('0.01')), 'carried_in': carried,
            'commission': utils.commission_for(base, affiliate.revshare_percent), 'customers': result.customers}


def statements(affiliate: Affiliate, *, limit: int = 31) -> list[dict]:
    rows = affiliate.net_loss_days.select_related('commission').order_by('-day')[:limit]
    return [{
        'day': r.day, 'customers': r.customers, 'stakes': r.stakes, 'wins': r.wins,
        'bonus_conversions': r.bonus_conversions, 'open_adjustment': r.open_in - r.open_out, 'hedge': r.hedge,
        'net_loss': r.net_loss, 'carried_in': r.carried_in, 'carry_out': r.carry_out, 'rate': r.rate,
        'commission': r.commission.amount if r.commission else ZERO,
        'status': r.commission.status if r.commission else '',
    } for r in rows]
