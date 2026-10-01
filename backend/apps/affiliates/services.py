"""affiliates domain logic — the ONLY place affiliate mutations happen.

Flow: a visitor lands on `/?ref=CODE` (click logged), registers (the referral is
fixed to that affiliate), and plays. Each month the affiliate earns their
revenue-share percentage of the net gaming revenue (NGR) of every player they
referred, read from the wallet ledger; optionally a one-off CPA once a referral
has deposited enough. Commissions are paid into the affiliate's own wallet with
a deterministic idempotency key, after operator approval (or automatically when
AFFILIATE_AUTO_PAY is on).
"""
from __future__ import annotations

from datetime import date, datetime, time
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts import services as accounts_services
from apps.wallet import services as wallet_services

from . import helpers, utils
from .models import Affiliate, AffiliateClick, Commission, Referral


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
    for _ in range(5):
        try:
            with transaction.atomic():
                return Affiliate.objects.create(
                    player_id=player_id,
                    code=wanted or helpers.suggested_code(player.username),
                    status=Affiliate.Status.ACTIVE if auto else Affiliate.Status.PENDING,
                    approved_at=timezone.now() if auto else None,
                    revshare_percent=Decimal(str(_setting('AFFILIATE_DEFAULT_REVSHARE', 25))),
                    cpa_amount=Decimal(str(_setting('AFFILIATE_DEFAULT_CPA', 0))),
                    cpa_min_deposit=Decimal(str(_setting('AFFILIATE_DEFAULT_CPA_MIN_DEPOSIT', 20))),
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
    """Operator edits: code, revshare_percent, cpa_amount, cpa_min_deposit, note.
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
    for name, limit in (('revshare_percent', Decimal('100')), ('cpa_amount', None), ('cpa_min_deposit', None)):
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
    from django.db.models import Sum

    today = timezone.localdate()
    month = utils.month_start(today)
    this_month = referral_stats(affiliate, start=_aware(month))
    lifetime = referral_stats(affiliate)
    ngr = sum((s['ngr'] for s in this_month.values()), Decimal('0'))
    by_status = dict(
        affiliate.commissions.values('status').annotate(total=Sum('amount')).values_list('status', 'total'),
    )
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
        'estimated_commission': utils.commission_for(ngr, affiliate.revshare_percent),
        'pending': (by_status.get('pending') or Decimal('0')) + (by_status.get('approved') or Decimal('0')),
        'paid': by_status.get('paid') or Decimal('0'),
        'referrals': referrals,
    }


# -- commissions ----------------------------------------------------------------

def _auto_pay(commission: Commission) -> Commission:
    if _setting('AFFILIATE_AUTO_PAY', False):
        return approve(commission.id)
    return commission


def compute_revshare(affiliate: Affiliate, period: date) -> Optional[Commission]:
    """Revenue share for one calendar month. Idempotent (one per affiliate per
    month); a month with no positive revenue records nothing."""
    period = utils.month_start(period)
    existing = affiliate.commissions.filter(kind=Commission.Kind.REVSHARE, period=period).first()
    if existing is not None:
        return existing
    stats = referral_stats(affiliate, start=_aware(period), end=_aware(utils.next_month(period)))
    ngr = sum((s['ngr'] for s in stats.values()), Decimal('0'))
    amount = utils.commission_for(ngr, affiliate.revshare_percent)
    if amount <= 0:
        return None
    try:
        with transaction.atomic():
            commission = Commission.objects.create(
                affiliate=affiliate, kind=Commission.Kind.REVSHARE, period=period,
                base_amount=ngr, rate=affiliate.revshare_percent, amount=amount,
                active_players=sum(1 for s in stats.values() if s['active']),
            )
    except IntegrityError:
        return affiliate.commissions.get(kind=Commission.Kind.REVSHARE, period=period)
    return _auto_pay(commission)


def compute_cpa(affiliate: Affiliate) -> int:
    """CPA for every referral whose deposits have reached the affiliate's
    threshold (once per referral). Returns how many were created."""
    if affiliate.cpa_amount <= 0:
        return 0
    unpaid = affiliate.referrals.exclude(commissions__kind=Commission.Kind.CPA)
    ids = list(unpaid.values_list('player_id', flat=True))
    if not ids:
        return 0
    totals = wallet_services.totals_by_kind(ids)
    created = 0
    for referral in unpaid:
        deposits = totals.get(referral.player_id, {}).get('deposit', Decimal('0'))
        if deposits <= 0 or deposits < affiliate.cpa_min_deposit:
            continue
        try:
            with transaction.atomic():
                commission = Commission.objects.create(
                    affiliate=affiliate, kind=Commission.Kind.CPA, referral=referral,
                    base_amount=deposits, rate=affiliate.cpa_amount, amount=affiliate.cpa_amount,
                    active_players=1,
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


@transaction.atomic
def approve(commission_id: int) -> Commission:
    """Approve and pay: credit the affiliate's wallet with a keyed entry, then
    mark PAID. Safe to repeat; recovery re-drives APPROVED ones."""
    commission = Commission.objects.select_for_update().select_related('affiliate').get(pk=commission_id)
    if commission.status in (Commission.Status.PAID, Commission.Status.REJECTED):
        return commission
    if commission.status == Commission.Status.PENDING:
        commission.status = Commission.Status.APPROVED
        commission.decided_at = timezone.now()
        commission.save(update_fields=['status', 'decided_at'])
    return _pay(commission)


def _pay(commission: Commission) -> Commission:
    wallet_services.credit(
        player_id=commission.affiliate.player_id, amount=commission.amount, kind='affiliate',
        idempotency_key=helpers.commission_payout_key(commission.id),
        reference=f'affiliate:{commission.id}',
    )
    commission.status = Commission.Status.PAID
    commission.paid_at = timezone.now()
    commission.save(update_fields=['status', 'paid_at'])
    from apps.notifications import services as notif_services
    label = commission.period.strftime('%B %Y') if commission.period else 'a new depositing referral'
    notif_services.notify(
        player_id=commission.affiliate.player_id, kind='account_alert', title='Affiliate commission paid',
        body=f'{commission.amount} for {label} has been added to your balance.',
    )
    return commission


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
