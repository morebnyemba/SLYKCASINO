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
# Two tallies, each with its own rate and carry-forward: sports (the agent's
# rate) and Aviator / casino (the programme's Aviator rate). Bonus money only
# plays sports, so bonus turned into Winnings is a sports cost.
GAMES = {
    'sports': {'stakes': ('bet_stake',), 'wins': ('bet_payout', 'bet_reversal'), 'conversions': True},
    'casino': {'stakes': ('casino_debit',), 'wins': ('casino_credit',), 'conversions': False},
}
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

def ledger_money(player_ids: Iterable[int], start: datetime, end: datetime, game: str = 'sports') -> dict[int, Money]:
    """Each player's real-money stakes and winnings on one game (sports or
    casino) in [start, end), and for sports the bonus turned into Winnings."""
    from apps.wallet.models import Bucket, LedgerEntry

    ids = list(player_ids)
    out: dict[int, Money] = defaultdict(Money)
    if not ids or start >= end:
        return out
    g = GAMES[game]
    cash = (Bucket.DEPOSIT, Bucket.WINNINGS)
    wanted = Q(kind__in=g['stakes'] + g['wins'], bucket__in=cash)
    if g['conversions']:
        wanted |= Q(kind='bonus_conversion', bucket=Bucket.WINNINGS)
    rows = (LedgerEntry.objects.filter(wallet__player_id__in=ids, created_at__gte=start, created_at__lt=end)
            .filter(wanted).values('wallet__player_id', 'kind').annotate(total=Sum('amount')))
    for row in rows:
        m, total = out[row['wallet__player_id']], row['total'] or ZERO
        if row['kind'] in CASH_STAKES:
            m.stakes += -total
        elif row['kind'] == 'bonus_conversion':
            m.conversions += total
        else:
            m.wins += total
    return out


def open_stakes(player_ids: Iterable[int], at: datetime, game: str = 'sports') -> dict[int, Decimal]:
    """Real-money stakes these players had riding at `at` on one game: sports
    tickets, or Aviator bets and casino rounds, placed before it and settled
    after it (or not yet)."""
    from apps.casino.models import GameRound
    from apps.jet.models import JetBet
    from apps.sportsbook.models import Bet, BetSlip

    ids = list(player_ids)
    out: dict[int, Decimal] = defaultdict(lambda: ZERO)
    if not ids:
        return out
    riding = Q(settled_at__gte=at) | Q(settled_at__isnull=True)
    if game == 'casino':
        jet = (JetBet.objects.filter(riding, player_id__in=ids, created_at__lt=at, is_free=False).exclude(wallet='bonus')
               .filter(Q(settled_at__isnull=False) | Q(status='active')))
        for pid, stake in jet.values_list('player_id', 'stake'):
            out[pid] += stake
        rounds = (GameRound.objects.filter(riding, player_id__in=ids, created_at__lt=at, debit_confirmed=True)
                  .exclude(wallet='bonus').filter(Q(settled_at__isnull=False) | Q(status='pending')))
        for pid, stake in rounds.values_list('player_id', 'stake'):
            out[pid] += stake
        return out
    for model in (Bet, BetSlip):
        qs = (model.objects.filter(riding, player_id__in=ids, placed_at__lt=at)
              .exclude(wallet='bonus').exclude(status='pending')
              .filter(Q(settled_at__isnull=False) | Q(status__in=('accepting', 'open'))))
        for pid, stake, cashed, cashed_at in qs.values_list('player_id', 'stake', 'stake_cashed_out', 'cashed_out_at'):
            # A partial cash-out after `at` took that part of the stake off later.
            out[pid] += stake + (cashed if cashed_at and cashed_at >= at else ZERO)
    return out


def window_money(windows: dict[int, tuple[datetime, datetime]], game: str = 'sports') -> dict[int, Money]:
    """Money per player on one game over each player's own [start, end) window."""
    by_window: dict[tuple[datetime, datetime], list[int]] = defaultdict(list)
    for pid, w in windows.items():
        if w[0] < w[1]:
            by_window[w].append(pid)
    out: dict[int, Money] = {}
    for (start, end), ids in by_window.items():
        money = ledger_money(ids, start, end, game)
        opened, closed = open_stakes(ids, start, game), open_stakes(ids, end, game)
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
    sports: Money = field(default_factory=Money)
    casino: Money = field(default_factory=Money)
    sports_hedge: Decimal = ZERO
    casino_hedge: Decimal = ZERO

    @property
    def sports_net(self) -> Decimal:
        return self.sports.net + self.sports_hedge

    @property
    def casino_net(self) -> Decimal:
        return self.casino.net + self.casino_hedge

    @property
    def pool(self) -> Money:
        both = Money()
        both.add(self.sports)
        both.add(self.casino)
        return both

    @property
    def hedge(self) -> Decimal:
        return self.sports_hedge + self.casino_hedge

    @property
    def net_loss(self) -> Decimal:
        return self.sports_net + self.casino_net


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
    others = {affiliate.player_id} | (outsiders if outsiders is not None else linked_outsiders(affiliate, windows))
    others -= set(windows)
    for game in GAMES:
        pool = getattr(result, game)
        for m in window_money(windows, game).values():
            pool.add(m)
        for m in window_money({pid: (start, end) for pid in others}, game).values():
            # Their winnings count against the pool; their losses earn nothing.
            setattr(result, f'{game}_hedge', getattr(result, f'{game}_hedge') + min(m.net, ZERO))
    return result


def _pct(value: Decimal) -> str:
    return f'{Decimal(value).normalize():f}'


def aviator_rate(programme: AffiliateProgramme) -> Decimal:
    return programme.aviator_commission_percent


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
        casino_carried = last.casino_carry_out if last else ZERO
        outsiders = linked_outsiders(affiliate, affiliate.referrals.values_list('player_id', flat=True))
        av_rate = aviator_rate(programme)
        while day < today and closed < MAX_DAYS_PER_RUN:
            start, end = _bounds(affiliate, day, programme)
            result = day_result(affiliate, start, end, programme=programme, outsiders=outsiders)
            base, carry_out = utils.carry(result.sports_net, carried, programme.negative_carryover)
            casino_base, casino_carry_out = utils.carry(result.casino_net, casino_carried, programme.negative_carryover)
            sports_amount = utils.commission_for(base, affiliate.revshare_percent)
            casino_amount = utils.commission_for(casino_base, av_rate)
            amount = sports_amount + casino_amount
            commission = None
            if amount > 0:
                review = programme.net_loss_review_above
                commission = Commission.objects.create(
                    affiliate=affiliate, kind=Commission.Kind.NET_LOSS, period=day,
                    base_amount=max(base, ZERO) + max(casino_base, ZERO), rate=affiliate.revshare_percent,
                    amount=amount, active_players=result.customers,
                    note=(f'Sports {_pct(affiliate.revshare_percent)}% of {max(base, ZERO):.2f} = {sports_amount:.2f}; '
                          f'Aviator & casino {_pct(av_rate)}% of {max(casino_base, ZERO):.2f} = {casino_amount:.2f}')[:500],
                    status=(Commission.Status.PENDING if review and amount > review else Commission.Status.APPROVED),
                    decided_at=timezone.now(),
                )
            pool = result.pool
            NetLossDay.objects.create(
                affiliate=affiliate, day=day, customers=result.customers, stakes=pool.stakes,
                wins=pool.wins, bonus_conversions=pool.conversions, open_in=pool.open_in,
                open_out=pool.open_out, hedge=result.hedge, net_loss=result.sports_net, carried_in=carried,
                carry_out=carry_out, rate=affiliate.revshare_percent, sports_commission=sports_amount,
                casino_net_loss=result.casino_net, casino_carried_in=casino_carried, casino_carry_out=casino_carry_out,
                casino_rate=av_rate, casino_commission=casino_amount, commission=commission,
            )
            carried, casino_carried = carry_out, casino_carry_out
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
    casino_carried = last.casino_carry_out if last else ZERO
    base, _ = utils.carry(result.sports_net, carried, programme.negative_carryover)
    casino_base, _ = utils.carry(result.casino_net, casino_carried, programme.negative_carryover)
    sports_c = utils.commission_for(base, affiliate.revshare_percent)
    casino_c = utils.commission_for(casino_base, aviator_rate(programme))
    return {'net_loss': result.net_loss.quantize(Decimal('0.01')), 'carried_in': carried + casino_carried,
            'sports_net_loss': result.sports_net.quantize(Decimal('0.01')),
            'casino_net_loss': result.casino_net.quantize(Decimal('0.01')),
            'sports_commission': sports_c, 'casino_commission': casino_c, 'aviator_rate': aviator_rate(programme),
            'commission': sports_c + casino_c, 'customers': result.customers}


def statements(affiliate: Affiliate, *, limit: int = 31) -> list[dict]:
    rows = affiliate.net_loss_days.select_related('commission').order_by('-day')[:limit]
    return [{
        'day': r.day, 'customers': r.customers, 'stakes': r.stakes, 'wins': r.wins,
        'bonus_conversions': r.bonus_conversions, 'open_adjustment': r.open_in - r.open_out, 'hedge': r.hedge,
        'net_loss': r.net_loss, 'carried_in': r.carried_in, 'carry_out': r.carry_out, 'rate': r.rate,
        'sports_commission': r.sports_commission, 'casino_net_loss': r.casino_net_loss,
        'casino_carried_in': r.casino_carried_in, 'casino_rate': r.casino_rate, 'casino_commission': r.casino_commission,
        'commission': r.commission.amount if r.commission else ZERO,
        'status': r.commission.status if r.commission else '',
    } for r in rows]
