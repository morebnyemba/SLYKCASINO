"""affiliates domain logic — the ONLY place affiliate mutations happen.

Flow: a visitor lands on `/?ref=CODE` (click logged), registers (the referral is
fixed to that affiliate), and plays. Each month the affiliate earns their
revenue-share percentage of the net gaming revenue (NGR) of every player they
referred, read from the wallet ledger; plus a one-off deposit commission once a
referral has deposited and played enough. Approved commissions (by an operator,
or automatically when AFFILIATE_AUTO_PAY is on) build up the affiliate's
balance, which they withdraw with a payout request: into their betting wallet
at once, or to mobile money / a bank once an operator has sent the money.
"""
from __future__ import annotations

import re
from datetime import date, datetime, time
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
    affiliate.status = status
    fields = ['status']
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
    'cpa_min_turnover_multiple': Decimal('100'),
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
    for flag in ('negative_carryover', 'external_payouts'):
        if values.get(flag) is not None:
            setattr(programme, flag, bool(values[flag]))
            fields.append(flag)
    if fields:
        programme.save(update_fields=[*fields, 'updated_at'])
    return programme


def on_deposit(*, player_id: int, amount: Decimal) -> None:
    """Called by the wallet for every new deposit. A referred player's FIRST
    deposit earns the welcome bonus (a % of it, capped), credited as bonus money
    that must be wagered before it can be withdrawn. Once per player."""
    if not Referral.objects.filter(player_id=player_id).exists():
        return
    if wallet_services.deposit_count(player_id) != 1:
        return  # only the first deposit
    programme = AffiliateProgramme.load()
    bonus = utils.welcome_bonus(
        Decimal(amount), programme.welcome_bonus_percent, programme.welcome_bonus_cap,
        programme.welcome_bonus_min_deposit,
    )
    if bonus <= 0:
        return
    from apps.promotions import services as promotions_services
    wagering = programme.welcome_bonus_wagering
    promotions_services.grant_bonus(
        player_id=player_id, amount=bonus, wagering_multiplier=wagering,
        system_code=WELCOME_BONUS_CODE, name='Welcome bonus',
        message=(f'{bonus} welcome bonus ({programme.welcome_bonus_percent.normalize():f}% of your first deposit) '
                 f'is in your wallet. Bet {(bonus * wagering).quantize(Decimal("0.01"))} in total to make it withdrawable.'),
    )


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


def dashboard(affiliate: Affiliate) -> dict:
    """What an affiliate (or an operator) sees: link stats, this month's
    running revenue and estimated commission, and money earned."""
    from datetime import timedelta

    today = timezone.localdate()
    month = utils.month_start(today)
    this_month = referral_stats(affiliate, start=_aware(month))
    lifetime = referral_stats(affiliate)
    ngr = sum((s['ngr'] for s in this_month.values()), Decimal('0'))
    names = accounts_services.usernames_for(list(lifetime))
    referrals = [
        {
            'player': utils.mask_username(names.get(r.player_id, '?')),
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
        'estimated_commission': utils.commission_for(
            utils.carry(ngr, carryover_balance(affiliate), AffiliateProgramme.load().negative_carryover)[0],
            affiliate.revshare_percent,
        ),
        **{k: money for k, money in balance(affiliate).items() if k != 'carryover'},
        'paid': balance(affiliate)['paid_out'],
        'referrals': referrals,
    }


# -- commissions ----------------------------------------------------------------

def _auto_pay(commission: Commission) -> Commission:
    if _setting('AFFILIATE_AUTO_PAY', False):
        return approve(commission.id)
    return commission


def carryover_balance(affiliate: Affiliate) -> Decimal:
    """The losing balance (<= 0) the affiliate carries into the next month."""
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
    """Daily job: last month's revenue share (once the month has closed) and any
    newly qualified CPAs, for every active affiliate."""
    today = today or timezone.localdate()
    period = utils.previous_month(today)
    revshare = cpa = 0
    for affiliate in Affiliate.objects.filter(status=Affiliate.Status.ACTIVE):
        if compute_revshare(affiliate, period) is not None:
            revshare += 1
        cpa += compute_cpa(affiliate)
    return {'period': period.isoformat(), 'revshare': revshare, 'cpa': cpa}


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
    _notify(commission.affiliate, 'Affiliate commission approved',
            f'{commission.amount} for {label} is in your affiliate balance — request a payout any time.')
    return commission


# -- balance & payouts -------------------------------------------------------------

def _sum(qs) -> Decimal:
    from django.db.models import Sum
    return (qs.aggregate(v=Sum('amount'))['v'] or Decimal('0')).quantize(Decimal('0.01'))


def balance(affiliate: Affiliate) -> dict:
    """The affiliate's money: approved commissions not yet paid out are
    `available`; `pending` awaits approval; `in_payout` is requested but not
    yet sent; `paid_out` is everything paid (including commissions paid
    straight to the wallet before payouts existed)."""
    approved = _sum(affiliate.commissions.filter(status=Commission.Status.APPROVED))
    requested = _sum(affiliate.payouts.filter(status=Payout.Status.REQUESTED))
    paid = _sum(affiliate.payouts.filter(status=Payout.Status.PAID))
    legacy = _sum(affiliate.commissions.filter(status=Commission.Status.PAID))
    return {
        'available': max(approved - requested - paid, Decimal('0.00')),
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
        'methods': [{'id': m.value, 'label': m.label} for m in methods],
        'min_payout': str(programme.min_payout),
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
    external = method != Payout.Method.WALLET
    if external:
        if not programme.external_payouts:
            raise AffiliateError('payouts to mobile money and banks are switched off — choose your betting wallet')
        if amount < programme.min_payout:
            raise AffiliateError(f'the minimum payout to {Payout.Method(method).label} is {programme.min_payout}')
        player = accounts_services.get_player(affiliate.player_id)
        if not player or player.kyc_status != player.Kyc.VERIFIED:
            raise AffiliateError('verify your identity before requesting a payout to mobile money or a bank')
        number = re.sub(r'[^0-9+]', '', account_number or '')
        if method in MOBILE_MONEY and not re.fullmatch(r'\+?\d{9,13}', number):
            raise AffiliateError('enter the mobile number to pay, e.g. 0771234567')
        if method == Payout.Method.BANK and (len(account_number.strip()) < 5 or not bank_name.strip() or not account_name.strip()):
            raise AffiliateError('enter the bank, account name and account number')
        account_number = number if method in MOBILE_MONEY else account_number.strip()
    available = balance(affiliate)['available']
    if amount > available:
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


@transaction.atomic
def complete_wallet_payout(payout_id: int) -> Payout:
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
    _notify(payout.affiliate, 'Affiliate earnings moved to your wallet',
            f'{payout.amount} from your affiliate balance is now in your betting wallet.')
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
