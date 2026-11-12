"""affiliates domain logic — the ONLY place affiliate mutations happen.

Flow: a visitor lands on `/?ref=CODE` (click logged), registers (the referral is
fixed to that affiliate), and plays. The affiliate (agent) earns their
percentage (30% by default) of the stake on every losing ticket a referred
player places, credited automatically a few minutes after it settles; plus a one-off deposit
commission once a referral has deposited and played enough, if the programme
offers one. A commission is final once it is approved: losing-ticket shares
straight away, deposit commissions when they qualify (or when an operator
approves them, if the programme asks for approval). With the programme's
`auto_payout` on (the default) final earnings go straight into the affiliate's
Winnings wallet, withdrawable like any winnings; otherwise they build up the
affiliate balance, withdrawn with a payout request (to the betting wallet at
once, or to mobile money / a bank once an operator has sent the money).
"""
from __future__ import annotations

import re
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts import services as accounts_services
from apps.wallet import services as wallet_services

from . import helpers, utils
from .models import Affiliate, AffiliateClick, AffiliateProgramme, Commission, Payout, Referral, RevshareMonth
from .reporting import affiliate_analytics, top_affiliates  # noqa: F401  (read-only analytics)


class AffiliateError(ValueError):
    """A request the affiliate programme can't accept (shown to the user)."""


def _setting(name: str, default):
    return getattr(settings, name, default)


def _aware(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min))


# -- membership ----------------------------------------------------------------

def get_for_player(player_id: int) -> Optional[Affiliate]:
    return Affiliate.objects.filter(player_id=player_id).first()


def get_active_by_code(code: str) -> Optional[Affiliate]:
    code = helpers.normalize_code(code)
    if not code:
        return None
    return Affiliate.objects.filter(code=code, status=Affiliate.Status.ACTIVE).first()


@transaction.atomic
def apply(*, player_id: int, website: str = '', code: str = '') -> Affiliate:
    """Join the programme. Pending until an operator approves, unless
    AFFILIATE_AUTO_APPROVE is on. Re-applying returns the existing record."""
    existing = get_for_player(player_id)
    if existing is not None:
        return existing
    player = accounts_services.get_player(player_id)
    if player is None:
        raise AffiliateError('player not found')
    if player.is_suspended or player.self_excluded:
        raise AffiliateError('this account cannot join the affiliate programme')

    wanted = helpers.normalize_code(code)
    if wanted and not helpers.is_valid_code(wanted):
        raise AffiliateError('codes are 3-24 letters or digits')
    if wanted and Affiliate.objects.filter(code=wanted).exists():
        raise AffiliateError('that code is taken — try another')
    auto = _setting('AFFILIATE_AUTO_APPROVE', False)
    programme = AffiliateProgramme.load()
    for _ in range(5):
        try:
            with transaction.atomic():
                return Affiliate.objects.create(
                    player_id=player_id,
                    code=wanted or helpers.suggested_code(player.username),
                    status=Affiliate.Status.ACTIVE if auto else Affiliate.Status.PENDING,
                    approved_at=timezone.now() if auto else None,
                    active_since=timezone.now() if auto else None,
                    revshare_percent=programme.default_revshare_percent,
                    cpa_amount=programme.default_cpa_amount,
                    cpa_min_deposit=programme.default_cpa_min_deposit,
                    cpa_percent=programme.default_cpa_percent,
                    cpa_cap=programme.default_cpa_cap,
                    website=website[:200],
                )
        except IntegrityError:
            if wanted:
                raise AffiliateError('that code is taken — try another')
            continue  # random suffix collided; draw another
    raise AffiliateError('could not allocate a referral code — try again')


def set_status(affiliate_id: int, status: str) -> Affiliate:
    if status not in Affiliate.Status.values:
        raise AffiliateError('unknown status')
    affiliate = Affiliate.objects.get(pk=affiliate_id)
    fields = ['status']
    if status == Affiliate.Status.ACTIVE and affiliate.status != status:
        affiliate.active_since = timezone.now()
        fields.append('active_since')
    affiliate.status = status
    if status == Affiliate.Status.ACTIVE and affiliate.approved_at is None:
        affiliate.approved_at = timezone.now()
        fields.append('approved_at')
    affiliate.save(update_fields=fields)
    return affiliate


def update_terms(affiliate_id: int, **terms) -> Affiliate:
    """Operator edits: code, revshare_percent, cpa_amount, cpa_min_deposit,
    cpa_percent, cpa_cap, note.
    New rates apply to periods computed from now on."""
    affiliate = Affiliate.objects.get(pk=affiliate_id)
    fields = []
    if terms.get('code') is not None:
        code = helpers.normalize_code(terms['code'])
        if not helpers.is_valid_code(code):
            raise AffiliateError('codes are 3-24 letters or digits')
        if Affiliate.objects.filter(code=code).exclude(pk=affiliate.pk).exists():
            raise AffiliateError('that code is taken')
        affiliate.code = code
        fields.append('code')
    for name, limit in (('revshare_percent', Decimal('100')), ('cpa_amount', None), ('cpa_min_deposit', None),
                        ('cpa_percent', Decimal('100')), ('cpa_cap', None)):
        if terms.get(name) is not None:
            value = Decimal(str(terms[name]))
            if value < 0 or (limit is not None and value > limit):
                raise AffiliateError(f'{name} is out of range')
            setattr(affiliate, name, value)
            fields.append(name)
    if terms.get('note') is not None:
        affiliate.note = str(terms['note'])[:500]
        fields.append('note')
    if fields:
        affiliate.save(update_fields=fields)
    return affiliate


# -- programme settings & the referred player's welcome bonus -------------------

PROGRAMME_FIELDS = {
    'min_payout': None,
    'welcome_bonus_percent': Decimal('100'), 'welcome_bonus_cap': None, 'welcome_bonus_wagering': Decimal('100'),
    'welcome_bonus_min_deposit': None, 'default_revshare_percent': Decimal('100'), 'default_cpa_amount': None,
    'default_cpa_min_deposit': None, 'default_cpa_percent': Decimal('100'), 'default_cpa_cap': None,
    'cpa_min_turnover_multiple': Decimal('100'), 'net_loss_review_above': None,
    'aviator_commission_percent': Decimal('100'),
}
WELCOME_BONUS_CODE = 'SYS-REFERRAL-WELCOME'


def get_programme() -> AffiliateProgramme:
    return AffiliateProgramme.load()


def update_programme(**values) -> AffiliateProgramme:
    """Operator edits to the programme settings (any subset of fields)."""
    programme = AffiliateProgramme.load()
    fields = []
    for name, limit in PROGRAMME_FIELDS.items():
        if values.get(name) is None:
            continue
        value = Decimal(str(values[name]))
        if value < 0 or (limit is not None and value > limit):
            raise AffiliateError(f'{name} is out of range')
        setattr(programme, name, value)
        fields.append(name)
    for flag in ('negative_carryover', 'external_payouts', 'auto_payout', 'auto_approve_commissions', 'lock_until_month_end'):
        if values.get(flag) is not None:
            setattr(programme, flag, bool(values[flag]))
            fields.append(flag)
    if fields:
        programme.save(update_fields=[*fields, 'updated_at'])
    return programme


def on_deposit(*, player_id: int, amount: Decimal) -> bool:
    """Called by the wallet for every new deposit. A referred player's FIRST
    deposit earns the welcome bonus (a % of it, capped), credited as bonus money
    that must be wagered before it can be withdrawn. Once per player. Returns
    whether it gave one."""
    if not Referral.objects.filter(player_id=player_id).exists():
        return False
    if wallet_services.deposit_count(player_id) != 1:
        return False  # only the first deposit
    programme = AffiliateProgramme.load()
    bonus = utils.welcome_bonus(
        Decimal(amount), programme.welcome_bonus_percent, programme.welcome_bonus_cap,
        programme.welcome_bonus_min_deposit,
    )
    if bonus <= 0:
        return False
    from apps.promotions import services as promotions_services
    wagering = programme.welcome_bonus_wagering
    promotions_services.grant_bonus(
        player_id=player_id, amount=bonus, wagering_multiplier=wagering,
        system_code=WELCOME_BONUS_CODE, name='Welcome bonus',
        message=(f'{bonus} welcome bonus ({programme.welcome_bonus_percent.normalize():f}% of your first deposit) '
                 f'is in your wallet. Bet {(bonus * wagering).quantize(Decimal("0.01"))} in total to make it withdrawable.'),
    )
    return True


# -- tracking ------------------------------------------------------------------

def record_click(code: str, *, campaign: str = '', landing: str = '') -> bool:
    affiliate = get_active_by_code(code)
    if affiliate is None:
        return False
    AffiliateClick.objects.create(affiliate=affiliate, campaign=campaign[:50], landing=landing[:200])
    return True


def attach_referral(*, player_id: int, code: str, campaign: str = '') -> Optional[Referral]:
    """Credit a new player's signup to the affiliate whose link they came
    through. Best-effort and silent: an unknown/inactive code or a
    self-referral simply isn't attributed."""
    affiliate = get_active_by_code(code)
    if affiliate is None or affiliate.player_id == player_id:
        return None
    try:
        with transaction.atomic():
            return Referral.objects.create(affiliate=affiliate, player_id=player_id, campaign=campaign[:50])
    except IntegrityError:
        return None  # already referred


# -- reporting -----------------------------------------------------------------

def referral_stats(affiliate: Affiliate, *, start=None, end=None) -> dict[int, dict]:
    """Per referred player: deposits and net gaming revenue in [start, end)."""
    ids = list(affiliate.referrals.values_list('player_id', flat=True))
    totals = wallet_services.totals_by_kind(ids, start=start, end=end)
    return {
        pid: {
            'deposits': totals.get(pid, {}).get('deposit', Decimal('0')),
            'ngr': utils.net_gaming_revenue(totals.get(pid, {})),
            'active': any(k in totals.get(pid, {}) for k in utils.GAMING_KINDS),
        }
        for pid in ids
    }


def _shown(name: str, mask: bool) -> str:
    """A customer's name as the viewer may see it: masked for the agent, in
    full for staff."""
    return utils.mask_username(name) if mask else name


def customer_rows(affiliate: Affiliate, referrals, *, mask: bool = True) -> list[dict]:
    """One page of an agent's customers: name, joined, campaign, whether they
    have deposited, and their net revenue this month."""
    ids = [r.player_id for r in referrals]
    month = utils.month_start(timezone.localdate())
    this_month = {pid: v for pid, v in referral_stats_for(ids, start=_aware(month)).items()}
    lifetime = referral_stats_for(ids)
    names = accounts_services.usernames_for(ids)
    return [{
        'player': _shown(names.get(r.player_id, '?'), mask),
        'joined': r.created_at,
        'campaign': r.campaign,
        'deposited': lifetime.get(r.player_id, {}).get('deposits', Decimal('0')) > 0,
        'ngr_this_month': this_month.get(r.player_id, {}).get('ngr', Decimal('0')),
    } for r in referrals]


def referral_stats_for(ids: list[int], *, start=None, end=None) -> dict[int, dict]:
    totals = wallet_services.totals_by_kind(ids, start=start, end=end)
    return {pid: {'deposits': totals.get(pid, {}).get('deposit', Decimal('0')),
                  'ngr': utils.net_gaming_revenue(totals.get(pid, {})),
                  'active': any(k in totals.get(pid, {}) for k in utils.GAMING_KINDS)} for pid in ids}


def dashboard(affiliate: Affiliate, *, mask: bool = True) -> dict:
    """What an affiliate (or an operator) sees: link stats, this month's
    running revenue and estimated commission, and money earned."""
    today = timezone.localdate()
    month = utils.month_start(today)
    this_month = referral_stats(affiliate, start=_aware(month))
    lifetime = referral_stats(affiliate)
    ngr = sum((s['ngr'] for s in this_month.values()), Decimal('0'))
    names = accounts_services.usernames_for(list(lifetime))
    summary = commission_summary(affiliate, today)
    referrals = [
        {
            'player': _shown(names.get(r.player_id, '?'), mask),
            'joined': r.created_at,
            'campaign': r.campaign,
            'deposited': lifetime.get(r.player_id, {}).get('deposits', Decimal('0')) > 0,
            'ngr_this_month': this_month.get(r.player_id, {}).get('ngr', Decimal('0')),
        }
        for r in affiliate.referrals.all()[:100]
    ]
    return {
        'clicks_30d': affiliate.clicks.filter(created_at__gte=timezone.now() - timedelta(days=30)).count(),
        'clicks_total': affiliate.clicks.count(),
        'signups': len(lifetime),
        'depositors': sum(1 for s in lifetime.values() if s['deposits'] > 0),
        'active_this_month': sum(1 for s in this_month.values() if s['active']),
        'ngr_this_month': ngr,
        'carryover': carryover_balance(affiliate),
        **summary,
        'estimated_commission': summary['commission_month'],
        **{k: money for k, money in balance(affiliate).items() if k != 'carryover'},
        'paid': balance(affiliate)['paid_out'],
        'referrals': referrals,
        'tickets_today': tickets_on(affiliate, today),
    }


def tickets_on(affiliate: Affiliate, day: date) -> dict:
    """How the referred players' tickets placed on `day` are doing."""
    return tickets_between(affiliate, _aware(day), _aware(day + timedelta(days=1)))


def tickets_between(affiliate: Affiliate, start, end) -> dict:
    """How the referred players' tickets placed in [start, end) are doing."""
    from apps.sportsbook import admin_tickets

    ids = list(affiliate.referrals.values_list('player_id', flat=True))
    counts = admin_tickets.status_counts(admin_tickets.player_tickets(ids, start=start, end=end))
    return {
        'played': sum(n for st, n in counts.items() if st not in ('pending', 'rejected')),
        'won': counts.get('won', 0),
        'lost': counts.get('lost', 0),
        'open': counts.get('open', 0) + counts.get('accepting', 0),
    }


TICKET_STATUSES = ('open', 'won', 'lost', 'void')

# The periods an agent can pick on their dashboard; a custom range can span up
# to ten years (see common.timeframes).
REPORT_FRAMES = ('today', 'yesterday', '7d', '30d', '90d', 'this_month', 'last_month', 'this_year', 'custom')
REPORT_PAGE = 50
MAX_YEARS_BACK = 10


def period_report(affiliate: Affiliate, frame: str = 'today', *, start: Optional[str] = None,
                  end: Optional[str] = None, page: int = 1, mask: bool = True) -> dict:
    """The agent's numbers for one period: their customers' deposits (with
    one page of the deposits themselves), tickets, link clicks, sign-ups and
    the commission on tickets lost in it. Raises TimeframeError for an unknown
    period, or a custom range more than ten years long or reaching further
    back than ten years."""
    from common import timeframes

    from .reporting import lost_stakes_between

    if frame not in REPORT_FRAMES:
        raise timeframes.TimeframeError(f'unknown timeframe: {frame}')
    window = timeframes.resolve(frame, start=start, end=end)
    today = timezone.localdate()
    oldest = date(today.year - MAX_YEARS_BACK, today.month, min(today.day, 28 if today.month == 2 else 31))
    if window.start < _aware(oldest):
        raise timeframes.TimeframeError(f'you can look back up to {MAX_YEARS_BACK} years (from {oldest.isoformat()})')
    s, e = window.start, window.end
    ids = list(affiliate.referrals.values_list('player_id', flat=True))
    page = max(1, int(page or 1))
    deposits = wallet_services.deposits_between(ids, s, e, offset=(page - 1) * REPORT_PAGE, limit=REPORT_PAGE)
    names = accounts_services.usernames_for(list({d['player_id'] for d in deposits['items']}))
    lost, losing_tickets, _ = lost_stakes_between(ids, s, e)
    clicks = affiliate.clicks.filter(created_at__gte=s, created_at__lt=e).count()
    signups = affiliate.referrals.filter(created_at__gte=s, created_at__lt=e).count()
    return {
        'frame': window.frame, 'label': window.label,
        'start': timezone.localdate(s).isoformat(), 'end': timezone.localdate(e - timedelta(microseconds=1)).isoformat(),
        'oldest': oldest.isoformat(),
        'deposits': {
            'total': f"{deposits['total']:.2f}", 'count': deposits['count'], 'depositors': deposits['depositors'],
            'items': [{'customer': _shown(names.get(d['player_id'], '?'), mask), 'amount': f"{d['amount']:.2f}",
                       'at': d['created_at']} for d in deposits['items']],
            'page': page, 'more': deposits['more'],
        },
        'tickets': tickets_between(affiliate, s, e),
        'clicks': clicks,
        'signups': signups,
        'lost_stakes': f'{lost:.2f}',
        'losing_tickets': losing_tickets,
        'commission': f'{utils.commission_for(lost, affiliate.revshare_percent):.2f}',
    }


def customer_tickets(affiliate: Affiliate, params, request, *, mask: bool = True) -> Optional[dict]:
    """A page of the referred players' tickets, newest first, each with the
    player's masked name (never their id or the ticket's code). None for a
    bad cursor. `params`: status (open|won|lost|void), cursor, limit."""
    from apps.sportsbook import admin_tickets

    ids = list(affiliate.referrals.values_list('player_id', flat=True))
    wanted = params.get('status') if params.get('status') in TICKET_STATUSES else ''
    everything = admin_tickets.player_tickets(ids)
    counts = admin_tickets.status_counts(everything)
    qs = {k: v.exclude(status__in=('pending', 'rejected')) for k, v in everything.items()}
    if wanted:
        qs = {k: v.filter(status=wanted) for k, v in qs.items()}
    page = admin_tickets.ticket_page(qs, params, {'request': request, 'skip_cashout': True})
    if page is None:
        return None
    rows, next_cursor = page
    names = accounts_services.usernames_for(list({r['player_id'] for r in rows}))
    for r in rows:
        r['customer'] = _shown(names.get(r.pop('player_id'), '?'), mask)
        r['code'] = ''
    return {
        'results': rows, 'next_cursor': next_cursor,
        'counts': {st: counts.get(st, 0) for st in TICKET_STATUSES},
    }


# -- commissions ----------------------------------------------------------------

def _auto_pay(commission: Commission) -> Commission:
    """A deposit/monthly commission that just qualified: final at once unless
    the programme asks staff to approve each one."""
    if AffiliateProgramme.load().auto_approve_commissions or _setting('AFFILIATE_AUTO_PAY', False):
        return approve(commission.id)
    return commission


def carryover_balance(affiliate: Affiliate) -> Decimal:
    """The losing balance (<= 0) the affiliate carries forward: their customers'
    net winnings not yet earned back (daily net loss; monthly under older terms)."""
    day = affiliate.net_loss_days.order_by('-day').first()
    if day is not None:
        return day.carry_out
    last = affiliate.revshare_months.order_by('-period').first()
    return last.carry_out if last else Decimal('0')


def compute_revshare(affiliate: Affiliate, period: date) -> Optional[Commission]:
    """Revenue share for one calendar month. Idempotent (one record per
    affiliate per month). With carry-over on, a losing month's deficit is
    netted against the following months until earned back; otherwise a
    losing month simply pays nothing. Returns the commission, if any."""
    period = utils.month_start(period)
    done = affiliate.revshare_months.filter(period=period).select_related('commission').first()
    if done is not None:
        return done.commission
    existing = affiliate.commissions.filter(kind=Commission.Kind.REVSHARE, period=period).first()
    if existing is not None:
        return existing  # closed before month records existed
    stats = referral_stats(affiliate, start=_aware(period), end=_aware(utils.next_month(period)))
    ngr = sum((s['ngr'] for s in stats.values()), Decimal('0'))
    programme = AffiliateProgramme.load()
    previous = affiliate.revshare_months.filter(period__lt=period).order_by('-period').first()
    carried_in = previous.carry_out if previous else Decimal('0')
    base, carry_out = utils.carry(ngr, carried_in, programme.negative_carryover)
    amount = utils.commission_for(base, affiliate.revshare_percent)
    try:
        with transaction.atomic():
            commission = None
            if amount > 0:
                commission = Commission.objects.create(
                    affiliate=affiliate, kind=Commission.Kind.REVSHARE, period=period,
                    base_amount=base, rate=affiliate.revshare_percent, amount=amount,
                    active_players=sum(1 for s in stats.values() if s['active']),
                    note=(f'Month revenue {ngr} less {-carried_in} carried over from earlier losing months'
                          if programme.negative_carryover and carried_in < 0 else ''),
                )
            RevshareMonth.objects.create(
                affiliate=affiliate, period=period, ngr=ngr,
                carried_in=carried_in if programme.negative_carryover else Decimal('0'),
                carry_out=carry_out, commission=commission,
            )
    except IntegrityError:
        done = affiliate.revshare_months.filter(period=period).first()
        return done.commission if done else None
    return _auto_pay(commission) if commission else None


def compute_cpa(affiliate: Affiliate) -> int:
    """One-off commission per referral (flat CPA + a % of their first deposit,
    capped) once they qualify: total deposits at least cpa_min_deposit AND
    staked at least cpa_min_turnover_multiple × their first deposit — so a
    deposit that's withdrawn without playing never earns anything. Once per
    referral. Returns how many were created."""
    if affiliate.cpa_amount <= 0 and affiliate.cpa_percent <= 0:
        return 0
    unpaid = affiliate.referrals.exclude(commissions__kind=Commission.Kind.CPA)
    ids = list(unpaid.values_list('player_id', flat=True))
    if not ids:
        return 0
    totals = wallet_services.totals_by_kind(ids)
    firsts = wallet_services.first_deposit_amounts(ids)
    multiple = AffiliateProgramme.load().cpa_min_turnover_multiple
    created = 0
    for referral in unpaid:
        t = totals.get(referral.player_id, {})
        deposits = t.get('deposit', Decimal('0'))
        first = firsts.get(referral.player_id)
        if first is None or deposits <= 0 or deposits < affiliate.cpa_min_deposit:
            continue
        turnover = -(t.get('bet_stake', Decimal('0')) + t.get('casino_debit', Decimal('0')))
        if turnover < first * multiple:
            continue
        amount = utils.deposit_commission(first, affiliate.cpa_amount, affiliate.cpa_percent, affiliate.cpa_cap)
        if amount <= 0:
            continue
        try:
            with transaction.atomic():
                commission = Commission.objects.create(
                    affiliate=affiliate, kind=Commission.Kind.CPA, referral=referral,
                    base_amount=first, rate=affiliate.cpa_percent, amount=amount, active_players=1,
                    note=f'First deposit {first}: {affiliate.cpa_percent.normalize():f}%'
                         + (f' (cap {affiliate.cpa_cap})' if affiliate.cpa_cap > 0 else '')
                         + (f' + {affiliate.cpa_amount} flat' if affiliate.cpa_amount > 0 else ''),
                )
        except IntegrityError:
            continue
        created += 1
        _auto_pay(commission)
    return created


def run_commissions(*, today: Optional[date] = None) -> dict:
    """Recurring job: newly qualified CPAs for every active affiliate. (Losing
    tickets are credited on their own, see `credit_losing_tickets`.)"""
    cpa = sum(compute_cpa(a) for a in Affiliate.objects.filter(status=Affiliate.Status.ACTIVE))
    return {'cpa': cpa}


# A ticket's commission is credited this long after it settles (time for a
# mistaken result to be corrected first), and missed ones are picked up for
# this long after that (e.g. if the worker was down).
CREDIT_DELAY = timedelta(minutes=3)
CREDIT_LOOKBACK = timedelta(days=2)
# The hourly catch-up (and the staff audit) look back this far.
CATCH_UP_DAYS = 35
HEARTBEAT_KEY = 'affiliates:credit-losing-tickets:last-run'
HEALTH_STALE = timedelta(minutes=5)    # the job runs every minute
HEALTH_SLACK = timedelta(minutes=2)    # don't flag a ticket the next run will pay


def credit_losing_tickets(*, now: Optional[datetime] = None) -> int:
    """Every minute: give each active agent their share of the stake on every
    ticket a referred player lost, once the ticket has been settled for
    CREDIT_DELAY. Credited straight to the agent's balance (no approval).
    Each ticket is paid once (unique per ticket). Returns how many were paid.
    Anything this short window misses (workers down, a customer linked late) is
    picked up by `catch_up_losing_tickets`."""
    now = now or timezone.now()
    paid = _credit_tickets(since=now - CREDIT_DELAY - CREDIT_LOOKBACK, now=now)
    _heartbeat(now)
    return paid


def catch_up_losing_tickets(*, now: Optional[datetime] = None, days: int = CATCH_UP_DAYS) -> int:
    """Hourly safety net: credit every eligible losing ticket of the last `days`
    that the minute job missed — after a worker outage, say. Idempotent."""
    now = now or timezone.now()
    return _credit_tickets(since=now - timedelta(days=days), now=now)


def credit_missed_tickets(affiliate_id: int, *, player_id: Optional[int] = None) -> int:
    """Staff: credit every eligible losing ticket an agent's customers ever lost
    that hasn't been credited (all time, same rules as the automatic job)."""
    return _credit_tickets(since=None, now=timezone.now(), affiliate_id=affiliate_id, player_id=player_id)


def _heartbeat(now: datetime) -> None:
    from django.core.cache import cache
    try:
        cache.set(HEARTBEAT_KEY, now.isoformat(), timeout=None)
    except Exception:  # noqa: BLE001 — a cache outage must never stop crediting
        pass


def crediting_last_ran() -> Optional[datetime]:
    from django.core.cache import cache
    from django.utils.dateparse import parse_datetime
    try:
        raw = cache.get(HEARTBEAT_KEY)
    except Exception:  # noqa: BLE001
        return None
    return parse_datetime(raw) if raw else None


def _losing_tickets(since, until, player_ids):
    """(ref, pk, player_id, stake, settled_at) of lost singles and multiples."""
    from apps.sportsbook.models import Bet, BetSlip

    for prefix, model in (('S', Bet), ('M', BetSlip)):
        qs = model.objects.filter(status='lost', settled_at__lte=until, player_id__in=player_ids)
        if since is not None:
            qs = qs.filter(settled_at__gte=since)
        for pk, player_id, stake, settled_at in qs.values_list('pk', 'player_id', 'stake', 'settled_at').iterator():
            yield f'{prefix}{pk}', player_id, stake, settled_at


def _credited_refs(refs: list[str]) -> set[str]:
    done: set[str] = set()
    for i in range(0, len(refs), 1000):
        done.update(Commission.objects.filter(kind=Commission.Kind.STAKE, ticket__in=refs[i:i + 1000])
                    .values_list('ticket', flat=True))
    return done


def _legacy_until(until: datetime) -> datetime:
    """Losing tickets are paid one by one only if settled before the programme
    moved to daily net loss; everything after is in the agent's daily close."""
    since = AffiliateProgramme.load().net_loss_since
    return min(until, since) if since else until


def _why_not_counted(settled_at, referral: Referral, affiliate: Affiliate, since=None) -> str:
    """'' when a losing ticket earns its agent a share on its own, else why not
    (`since`: the programme's switch to daily net loss)."""
    if since and settled_at >= since:
        return 'net_loss'
    if settled_at < referral.counts_from:
        return 'before_link'
    if affiliate.active_since and settled_at < affiliate.active_since:
        return 'agent_inactive'
    if affiliate.revshare_percent <= 0:
        return 'zero_rate'
    return ''


def _credit_tickets(*, since, now, affiliate_id=None, player_id=None) -> int:
    """Credit each losing ticket settled in [since, now - CREDIT_DELAY] that a
    referred player lost while linked to an ACTIVE agent (and while that agent
    was active). Each ticket is paid once (unique per ticket)."""
    links = Referral.objects.filter(affiliate__status=Affiliate.Status.ACTIVE).select_related('affiliate')
    if affiliate_id is not None:
        links = links.filter(affiliate_id=affiliate_id)
    if player_id is not None:
        links = links.filter(player_id=player_id)
    by_player = {r.player_id: r for r in links}
    if not by_player:
        return 0
    tickets = list(_losing_tickets(since, _legacy_until(now - CREDIT_DELAY), list(by_player)))
    done = _credited_refs([t[0] for t in tickets])
    since = AffiliateProgramme.load().net_loss_since
    paid = 0
    for ref, pid, stake, settled_at in tickets:
        if ref in done:
            continue
        referral = by_player[pid]
        affiliate = referral.affiliate
        if _why_not_counted(settled_at, referral, affiliate, since):
            continue
        rate = affiliate.revshare_percent
        amount = utils.commission_for(stake, rate)
        if amount <= 0:
            continue
        try:
            with transaction.atomic():
                Commission.objects.create(
                    affiliate_id=affiliate.pk, kind=Commission.Kind.STAKE, ticket=ref,
                    period=timezone.localdate(settled_at), base_amount=stake, rate=rate, amount=amount,
                    active_players=1, status=Commission.Status.APPROVED, decided_at=now,
                )
        except IntegrityError:
            continue  # paid by a run that overlapped this one
        paid += 1
    if paid:
        pay_out_earnings()
    return paid


def ticket_audit(affiliate: Affiliate, *, days: int = CATCH_UP_DAYS, now: Optional[datetime] = None,
                 limit: int = 100) -> dict:
    """Staff: every losing ticket of an agent's customers in the last `days`,
    and whether it was credited — or why not. `missing` are tickets that should
    have been paid and weren't (the catch-up or 'Credit missed' pays them)."""
    now = now or timezone.now()
    by_player = {r.player_id: r for r in affiliate.referrals.all()}
    tickets = sorted(_losing_tickets(now - timedelta(days=days), now, list(by_player)),
                     key=lambda t: t[3], reverse=True) if by_player else []
    credited = dict(Commission.objects.filter(kind=Commission.Kind.STAKE, ticket__in=[t[0] for t in tickets])
                    .values_list('ticket', 'amount')) if tickets else {}
    names = accounts_services.usernames_for(list(by_player))
    since = AffiliateProgramme.load().net_loss_since
    counts = {'credited': 0, 'waiting': 0, 'missing': 0, 'not_counted': 0}
    missing_amount, rows = Decimal('0'), []
    for ref, pid, stake, settled_at in tickets:
        if ref in credited:
            state, reason, amount = 'credited', '', credited[ref]
        elif affiliate.status != Affiliate.Status.ACTIVE:
            state, reason, amount = 'not_counted', 'agent_inactive', Decimal('0')
        else:
            reason = _why_not_counted(settled_at, by_player[pid], affiliate, since)
            amount = Decimal('0') if reason else utils.commission_for(stake, affiliate.revshare_percent)
            state = 'not_counted' if reason else ('waiting' if settled_at > now - CREDIT_DELAY else 'missing')
            if state == 'missing':
                missing_amount += amount
        counts[state] += 1
        if len(rows) < limit:
            rows.append({'ticket': ref, 'customer': names.get(pid, f'#{pid}'), 'stake': stake, 'settled_at': settled_at,
                         'state': state, 'reason': reason, 'amount': amount})
    return {'days': days, 'customers': len(by_player), 'losing_tickets': len(tickets), 'counts': counts,
            'missing_amount': missing_amount.quantize(Decimal('0.01')), 'tickets': rows}


def crediting_health(*, now: Optional[datetime] = None) -> dict:
    """Staff: is the crediting job running, and is anything left unpaid?"""
    now = now or timezone.now()
    last = crediting_last_ran()
    missing, amount, agents = 0, Decimal('0'), set()
    links = {r.player_id: r for r in Referral.objects.filter(affiliate__status=Affiliate.Status.ACTIVE)
             .select_related('affiliate')}
    if links:
        tickets = list(_losing_tickets(now - timedelta(days=CATCH_UP_DAYS),
                                       _legacy_until(now - CREDIT_DELAY - HEALTH_SLACK), list(links)))
        done = _credited_refs([t[0] for t in tickets])
        since = AffiliateProgramme.load().net_loss_since
        for ref, pid, stake, settled_at in tickets:
            r = links[pid]
            if ref in done or _why_not_counted(settled_at, r, r.affiliate, since):
                continue
            missing += 1
            amount += utils.commission_for(stake, r.affiliate.revshare_percent)
            agents.add(r.affiliate_id)
    from . import netloss
    closed_at = netloss.last_close()
    return {
        'last_run': last, 'running': bool(last and now - last < HEALTH_STALE),
        'last_close': closed_at, 'closing': bool(closed_at and now - closed_at < timedelta(hours=2)),
        'days_behind': netloss.days_behind(), 'net_loss_since': AffiliateProgramme.load().net_loss_since,
        'missing_tickets': missing, 'missing_amount': amount.quantize(Decimal('0.01')), 'agents_affected': len(agents),
    }


@transaction.atomic
def link_customer(affiliate_id: int, player_id: int, *, credit_from: Optional[datetime] = None,
                  linked_by: str = '') -> tuple[Referral, int]:
    """Staff: link a customer to an agent (or move them from another agent) when
    the sign-up link was lost. Losing tickets count from `credit_from` (default:
    now); ones already credited to another agent stay theirs. Returns the link
    and how many past tickets were credited."""
    affiliate = Affiliate.objects.filter(pk=affiliate_id).first()
    if affiliate is None:
        raise AffiliateError('agent not found')
    if affiliate.status != Affiliate.Status.ACTIVE:
        raise AffiliateError('activate the agent first')
    if affiliate.player_id == player_id:
        raise AffiliateError('an agent can’t be their own customer')
    if accounts_services.get_player(player_id) is None:
        raise AffiliateError('player not found')
    now = timezone.now()
    start = min(credit_from or now, now)
    referral = Referral.objects.select_for_update().filter(player_id=player_id).first()
    if referral is None:
        referral = Referral.objects.create(affiliate=affiliate, player_id=player_id, campaign='staff',
                                           credit_from=start, linked_by=linked_by[:150])
    else:
        if referral.affiliate_id != affiliate.pk:
            referral.affiliate = affiliate
        referral.credit_from, referral.linked_by = start, linked_by[:150]
        referral.save(update_fields=['affiliate', 'credit_from', 'linked_by'])
    return referral, credit_missed_tickets(affiliate.pk, player_id=player_id)


def lost_stakes(affiliate: Affiliate, day: date) -> tuple[Decimal, int, int]:
    """(total stake, tickets, players) of the referred players' tickets that
    were settled as lost on `day` (local time)."""
    from .reporting import lost_stakes_between

    ids = list(affiliate.referrals.values_list('player_id', flat=True))
    return lost_stakes_between(ids, _aware(day), _aware(day + timedelta(days=1)))


def commission_summary(affiliate: Affiliate, today: date) -> dict:
    """What the agent has earned: today (credited, plus losing tickets still
    inside the few minutes before they're credited), this month, all time."""
    from django.db.models import Q

    from . import netloss

    stake, tickets, _ = lost_stakes(affiliate, today)
    earned = affiliate.commissions.exclude(status=Commission.Status.REJECTED)
    by_day = (Commission.Kind.STAKE, Commission.Kind.NET_LOSS)
    credited_today = earned.filter(kind__in=by_day, period=today)
    estimate = netloss.today_estimate(affiliate)
    on_its_way = estimate['commission']          # today's net loss so far, paid after midnight
    if not AffiliateProgramme.load().net_loss_since:   # per-ticket terms: tickets inside the 3-minute delay
        credited_stake = _sum_field(credited_today.filter(kind=Commission.Kind.STAKE), 'base_amount')
        on_its_way = utils.commission_for(stake - credited_stake, affiliate.revshare_percent)
    first = utils.month_start(today)
    month = _sum(earned.filter(Q(kind__in=by_day, period__gte=first)
                               | (~Q(kind__in=by_day) & Q(created_at__gte=_aware(first)))))
    return {
        'commission_rate': affiliate.revshare_percent,
        'commission_basis': 'net_loss',
        'aviator_commission_rate': AffiliateProgramme.load().aviator_commission_percent,
        'net_loss_today': estimate['net_loss'],
        'lost_stakes_today': stake,
        'losing_tickets_today': tickets,
        'commission_today': _sum(credited_today) + on_its_way,
        'commission_month': month + on_its_way,
        'commission_total': _sum(earned) + on_its_way,
    }


def _notify(affiliate: Affiliate, title: str, body: str) -> None:
    from apps.notifications import services as notif_services
    notif_services.notify(player_id=affiliate.player_id, kind='account_alert', title=title, body=body)


@transaction.atomic
def approve(commission_id: int) -> Commission:
    """Approve a commission: its amount joins the affiliate's balance, ready
    to withdraw. Idempotent."""
    commission = Commission.objects.select_for_update().select_related('affiliate').get(pk=commission_id)
    if commission.status != Commission.Status.PENDING:
        return commission
    commission.status = Commission.Status.APPROVED
    commission.decided_at = timezone.now()
    commission.save(update_fields=['status', 'decided_at'])
    label = commission.period.strftime('%B %Y') if commission.period else 'a new depositing referral'
    if AffiliateProgramme.load().auto_payout:
        pay_out_earnings(affiliate_id=commission.affiliate_id)
        _notify(commission.affiliate, 'Affiliate commission paid',
                f'{commission.amount} for {label} is in your Winnings wallet — you can withdraw it.')
    else:
        _notify(commission.affiliate, 'Affiliate commission approved',
                f'{commission.amount} for {label} is in your affiliate balance — request a payout any time.')
    return commission


# -- balance & payouts -------------------------------------------------------------

def _sum_field(qs, field: str) -> Decimal:
    from django.db.models import Sum
    return qs.aggregate(v=Sum(field))['v'] or Decimal('0')


def _sum(qs) -> Decimal:
    from django.db.models import Sum
    return (qs.aggregate(v=Sum('amount'))['v'] or Decimal('0')).quantize(Decimal('0.01'))


def _earned_on(c: Commission) -> date:
    """The day a commission was earned: a losing ticket's or net-loss day's
    period, otherwise when it became final."""
    if c.kind in (Commission.Kind.STAKE, Commission.Kind.NET_LOSS) and c.period:
        return c.period
    return timezone.localdate(c.decided_at or c.created_at)


def balance(affiliate: Affiliate, *, today: Optional[date] = None) -> dict:
    """The affiliate's money: approved commissions not yet paid out, split into
    `available` (free to move or withdraw) and `locked` (earned this month,
    while the programme locks earnings until month end; it unlocks on
    `unlocks_on`); `pending` awaits approval; `in_payout` is requested but not
    yet sent; `paid_out` is everything paid (including commissions paid
    straight to the wallet before payouts existed)."""
    today = today or timezone.localdate()
    approved_qs = affiliate.commissions.filter(status=Commission.Status.APPROVED)
    approved = _sum(approved_qs)
    requested = _sum(affiliate.payouts.filter(status=Payout.Status.REQUESTED))
    paid = _sum(affiliate.payouts.filter(status=Payout.Status.PAID))
    legacy = _sum(affiliate.commissions.filter(status=Commission.Status.PAID))
    left = max(approved - requested - paid, Decimal('0.00'))
    available, locked, unlocks_on = left, Decimal('0.00'), None
    if AffiliateProgramme.load().lock_until_month_end:
        month = utils.month_start(today)
        unlocked = sum((c.amount for c in approved_qs.only('kind', 'period', 'amount', 'decided_at', 'created_at')
                        if _earned_on(c) < month), Decimal('0.00'))
        available = min(max(unlocked - requested - paid, Decimal('0.00')), left)
        locked = left - available
        unlocks_on = utils.next_month(today) if locked > 0 else None
    return {
        'available': available.quantize(Decimal('0.01')),
        'locked': locked.quantize(Decimal('0.01')),
        'unlocks_on': unlocks_on,
        'pending': _sum(affiliate.commissions.filter(status=Commission.Status.PENDING)),
        'in_payout': requested,
        'paid_out': paid + legacy,
        'carryover': carryover_balance(affiliate),
    }


MOBILE_MONEY = (Payout.Method.ECOCASH, Payout.Method.ONEMONEY, Payout.Method.INNBUCKS)


def payout_options(affiliate: Affiliate) -> dict:
    programme = AffiliateProgramme.load()
    player = accounts_services.get_player(affiliate.player_id)
    methods = [Payout.Method.WALLET]
    if programme.external_payouts:
        methods += [*MOBILE_MONEY, Payout.Method.BANK]
    return {
        'methods': [{'id': m.value, 'label': 'Move to my Winnings wallet' if m == Payout.Method.WALLET else m.label}
                    for m in methods],
        'min_payout': str(programme.min_payout),
        'lock_until_month_end': programme.lock_until_month_end,
        # Earnings go straight into the Winnings wallet: withdraw them from there.
        'auto_payout': programme.auto_payout,
        'kyc_verified': bool(player and player.kyc_status == player.Kyc.VERIFIED),
    }


@transaction.atomic
def request_payout(
    *, affiliate_id: int, amount, method: str, account_name: str = '', account_number: str = '', bank_name: str = '',
) -> Payout:
    """Withdraw from the affiliate balance. To the betting wallet it's paid at
    once; mobile money and bank payouts wait for an operator. Locked per
    affiliate so two requests can never spend the same balance."""
    affiliate = Affiliate.objects.select_for_update().get(pk=affiliate_id)
    if affiliate.status != Affiliate.Status.ACTIVE:
        raise AffiliateError('only active affiliates can request payouts')
    try:
        amount = Decimal(str(amount)).quantize(Decimal('0.01'))
    except (ArithmeticError, ValueError):
        raise AffiliateError('enter a valid amount')
    if amount <= 0:
        raise AffiliateError('enter a valid amount')
    if method not in Payout.Method.values:
        raise AffiliateError('choose how you want to be paid')
    programme = AffiliateProgramme.load()
    if amount < programme.min_payout:
        raise AffiliateError(f'the minimum withdrawal is {programme.min_payout}')
    external = method != Payout.Method.WALLET
    if external:
        if not programme.external_payouts:
            raise AffiliateError('payouts to mobile money and banks are switched off — choose your betting wallet')
        player = accounts_services.get_player(affiliate.player_id)
        if not player or player.kyc_status != player.Kyc.VERIFIED:
            raise AffiliateError('verify your identity before requesting a payout to mobile money or a bank')
        number = re.sub(r'[^0-9+]', '', account_number or '')
        if method in MOBILE_MONEY and not re.fullmatch(r'\+?\d{9,13}', number):
            raise AffiliateError('enter the mobile number to pay, e.g. 0771234567')
        if method == Payout.Method.BANK and (len(account_number.strip()) < 5 or not bank_name.strip() or not account_name.strip()):
            raise AffiliateError('enter the bank, account name and account number')
        account_number = number if method in MOBILE_MONEY else account_number.strip()
    money = balance(affiliate)
    available = money['available']
    if amount > available:
        if money['locked'] > 0 and amount <= available + money['locked']:
            raise AffiliateError(f'{money["locked"]} is this month’s earnings and unlocks on {money["unlocks_on"]:%d %b} — '
                                 f'you can move or withdraw up to {available} now')
        raise AffiliateError(f'you can withdraw up to {available}')
    payout = Payout.objects.create(
        affiliate=affiliate, amount=amount, method=method,
        account_name=account_name.strip()[:120] if external else '',
        account_number=account_number[:60] if external else '',
        bank_name=bank_name.strip()[:80] if method == Payout.Method.BANK else '',
    )
    if not external:
        return complete_wallet_payout(payout.id)
    _notify(affiliate, 'Payout requested',
            f'We’ve received your request for {amount} to {payout.get_method_display()}. You’ll be notified when it’s sent.')
    return payout


AUTO_PAYOUT_NOTE = 'Paid automatically'


def _unpaid_affiliate_ids() -> list[int]:
    """Active affiliates whose approved earnings exceed what has been paid or
    requested — one grouped query each way, however many affiliates there are."""
    from django.db.models import Sum
    earned = dict(Commission.objects.filter(status=Commission.Status.APPROVED, affiliate__status=Affiliate.Status.ACTIVE)
                  .values_list('affiliate_id').annotate(t=Sum('amount')))
    if not earned:
        return []
    spent = dict(Payout.objects.filter(affiliate_id__in=list(earned), status__in=(Payout.Status.REQUESTED, Payout.Status.PAID))
                 .values_list('affiliate_id').annotate(t=Sum('amount')))
    return [a for a, t in earned.items() if t - (spent.get(a) or Decimal('0')) >= Decimal('0.01')]


def pay_out_earnings(*, affiliate_id: Optional[int] = None) -> dict:
    """Pay final earnings straight into each active affiliate's Winnings wallet
    (programme `auto_payout`). Runs whenever a commission becomes final and every
    minute as a sweep (earnings from before it was switched on, a declined
    mobile-money payout returning to the balance). Each affiliate is locked
    while paid, and each payout is keyed, so overlapping runs never pay twice.
    Money already requested to mobile money / a bank is left alone. Returns
    {affiliates, amount}."""
    paid, total = 0, Decimal('0')
    if not AffiliateProgramme.load().auto_payout:
        return {'affiliates': 0, 'amount': '0.00'}
    for aid in ([affiliate_id] if affiliate_id else _unpaid_affiliate_ids()):
        try:
            with transaction.atomic():
                affiliate = Affiliate.objects.select_for_update().filter(pk=aid, status=Affiliate.Status.ACTIVE).first()
                if affiliate is None:
                    continue
                amount = balance(affiliate)['available']
                if amount < Decimal('0.01'):
                    continue
                payout = Payout.objects.create(affiliate=affiliate, amount=amount, method=Payout.Method.WALLET,
                                               note=AUTO_PAYOUT_NOTE)
                complete_wallet_payout(payout.id, notify=False)
        except Exception:  # noqa: BLE001 — one affiliate must never stop the rest
            import logging
            logging.getLogger(__name__).exception('automatic affiliate payout failed for %s', aid)
            continue
        paid += 1
        total += amount
    return {'affiliates': paid, 'amount': f'{total:.2f}'}


@transaction.atomic
def complete_wallet_payout(payout_id: int, *, notify: bool = True) -> Payout:
    """Move a wallet payout into the affiliate's betting wallet (keyed, so a
    retry or recovery can never pay twice), then mark it paid."""
    payout = Payout.objects.select_for_update().select_related('affiliate').get(pk=payout_id)
    if payout.status != Payout.Status.REQUESTED or payout.method != Payout.Method.WALLET:
        return payout
    wallet_services.credit(
        player_id=payout.affiliate.player_id, amount=payout.amount, kind='affiliate',
        idempotency_key=helpers.payout_wallet_key(payout.id), reference=f'affiliate-payout:{payout.id}',
    )
    payout.status = Payout.Status.PAID
    payout.decided_at = timezone.now()
    payout.save(update_fields=['status', 'decided_at'])
    if notify:
        _notify(payout.affiliate, 'Affiliate earnings moved to your wallet',
                f'{payout.amount} from your affiliate balance is now in your Winnings wallet.')
    return payout


@transaction.atomic
def mark_payout_paid(payout_id: int, *, reference: str = '', note: str = '') -> Payout:
    """Operator: the money has been sent (EcoCash/bank) — record the reference."""
    payout = Payout.objects.select_for_update().select_related('affiliate').get(pk=payout_id)
    if payout.status != Payout.Status.REQUESTED:
        raise AffiliateError(f'this payout is already {payout.status}')
    if payout.method == Payout.Method.WALLET:
        return complete_wallet_payout(payout.id)
    payout.status = Payout.Status.PAID
    payout.reference = reference.strip()[:100]
    payout.note = note.strip()[:500]
    payout.decided_at = timezone.now()
    payout.save(update_fields=['status', 'reference', 'note', 'decided_at'])
    _notify(payout.affiliate, 'Payout sent',
            f'{payout.amount} has been sent to your {payout.get_method_display()} ({payout.account_number})'
            + (f' — reference {payout.reference}.' if payout.reference else '.'))
    return payout


@transaction.atomic
def reject_payout(payout_id: int, *, note: str = '') -> Payout:
    """Operator: decline a payout request; the amount returns to the balance."""
    payout = Payout.objects.select_for_update().select_related('affiliate').get(pk=payout_id)
    if payout.status != Payout.Status.REQUESTED:
        raise AffiliateError(f'this payout is already {payout.status}')
    payout.status = Payout.Status.REJECTED
    payout.note = note.strip()[:500]
    payout.decided_at = timezone.now()
    payout.save(update_fields=['status', 'note', 'decided_at'])
    _notify(payout.affiliate, 'Payout not sent',
            f'Your payout of {payout.amount} was declined' + (f': {payout.note}' if payout.note else '.')
            + ' The amount is back in your affiliate balance.')
    return payout


@transaction.atomic
def reject(commission_id: int, note: str = '') -> Commission:
    commission = Commission.objects.select_for_update().get(pk=commission_id)
    if commission.status != Commission.Status.PENDING:
        raise AffiliateError(f'a {commission.status} commission cannot be rejected')
    commission.status = Commission.Status.REJECTED
    commission.decided_at = timezone.now()
    commission.note = note[:500]
    commission.save(update_fields=['status', 'decided_at', 'note'])
    return commission


# -- account deletion ---------------------------------------------------------------

def money_owed_to(player_id: int) -> Decimal:
    """Affiliate earnings a player still has (available or being paid out)."""
    affiliate = get_for_player(player_id)
    if affiliate is None:
        return Decimal('0')
    b = balance(affiliate)
    return b['available'] + b['in_payout']


def erase_player_data(player_id: int) -> int:
    """Permanently delete a player's affiliate side: their own affiliate account
    (clicks, commissions, payouts, months; the players they referred simply stop
    being attributed) and their record as someone else's referral (that
    affiliate keeps any commission already earned on them)."""
    deleted = 0
    referral = Referral.objects.filter(player_id=player_id).first()
    if referral is not None:
        Commission.objects.filter(referral=referral).update(referral=None)
        deleted += Referral.objects.filter(pk=referral.pk).delete()[0]
    affiliate = get_for_player(player_id)
    if affiliate is not None:
        RevshareMonth.objects.filter(affiliate=affiliate).delete()
        deleted += Payout.objects.filter(affiliate=affiliate).delete()[0]
        Commission.objects.filter(affiliate=affiliate).delete()
        deleted += Affiliate.objects.filter(pk=affiliate.pk).delete()[0]
    return deleted
