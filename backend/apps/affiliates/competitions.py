"""Agent competitions, and staff adjustments to an agent's locked balance.

A competition sets targets for a date window — new customers, their deposits,
or both — and a prize. Progress for an agent:

* customers: people who joined with the agent's link or code in the window
  (counted only once they've deposited at least `min_customer_deposit` in the
  window, when that's set — so fake sign-ups don't win prizes);
* deposits: everything the agent's customers (new or old) deposited in the window.

Every agent who reaches every target that's set gets the prize once (the
unique award row makes a second award impossible), as an approved `prize`
commission. Commissions earned this month are locked until the month ends, so
the prize lands in the agent's locked balance. `award_due()` runs every 15
minutes and when the pages load.

Staff can also add to or take from an agent's locked balance (`adjust_locked`):
an approved `adjust` commission, positive or negative.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.accounts import services as accounts_services

from .models import Affiliate, AffiliateCompetition, Commission, CompetitionAward

CENT = Decimal('0.01')
ZERO = Decimal('0.00')


class CompetitionError(ValueError):
    """A reason shown to staff."""


def _aware(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min))


def window(c: AffiliateCompetition) -> tuple[datetime, datetime]:
    return _aware(c.starts_on), _aware(c.ends_on + timedelta(days=1))


def status_of(c: AffiliateCompetition, today: Optional[date] = None) -> str:
    today = today or timezone.localdate()
    if not c.active:
        return 'off'
    if today < c.starts_on:
        return 'upcoming'
    if today > c.ends_on:
        return 'ended'
    return 'running'


def progress(c: AffiliateCompetition, affiliate: Affiliate) -> dict:
    """An agent's progress towards a competition's targets."""
    from apps.wallet import services as wallet_services
    start, end = window(c)
    all_ids = list(affiliate.referrals.values_list('player_id', flat=True))
    new_ids = list(affiliate.referrals.filter(created_at__gte=start, created_at__lt=end).values_list('player_id', flat=True))
    totals = wallet_services.totals_by_kind(all_ids, start=start, end=end) if all_ids else {}
    deposits = sum((totals.get(pid, {}).get('deposit', ZERO) for pid in all_ids), ZERO).quantize(CENT)
    if c.min_customer_deposit > 0:
        customers = sum(1 for pid in new_ids if totals.get(pid, {}).get('deposit', ZERO) >= c.min_customer_deposit)
    else:
        customers = len(new_ids)
    parts = []
    if c.target_customers:
        parts.append(min(customers / c.target_customers, 1))
    if c.target_deposits > 0:
        parts.append(min(float(deposits / c.target_deposits), 1))
    reached = bool(parts) and all(p >= 1 for p in parts)
    return {'customers': customers, 'deposits': str(deposits), 'reached': reached,
            'percent': round(100 * (min(parts) if parts else 0))}


def _award(c: AffiliateCompetition, affiliate: Affiliate, prog: dict) -> Optional[CompetitionAward]:
    now = timezone.now()
    try:
        with transaction.atomic():
            commission = Commission.objects.create(
                affiliate=affiliate, kind=Commission.Kind.PRIZE, amount=c.prize, base_amount=ZERO, rate=ZERO,
                status=Commission.Status.APPROVED, decided_at=now, note=f'Competition: {c.name}'[:255])
            award = CompetitionAward.objects.create(competition=c, affiliate=affiliate, commission=commission,
                                                    customers=prog['customers'], deposits=Decimal(prog['deposits']))
    except IntegrityError:
        return None                                    # already awarded (a parallel run won the race)
    accounts_services.audit(affiliate.player_id, 'affiliate_competition_won', None, competition=c.id,
                            prize=str(c.prize), customers=prog['customers'], deposits=prog['deposits'])
    try:
        from apps.notifications import services as notif
        notif.notify(player_id=affiliate.player_id, kind='account_alert', title=f'You won “{c.name}”',
                     body=f'${c.prize:.2f} prize added to your agent balance (locked until the month ends).')
    except Exception:  # noqa: BLE001 — a notification must never undo the award
        pass
    return award


def award_due(*, today: Optional[date] = None) -> int:
    """Give the prize to every agent who has reached a running (or just ended)
    competition and hasn't had it. Idempotent. Returns how many were awarded."""
    today = today or timezone.localdate()
    awarded = 0
    comps = AffiliateCompetition.objects.filter(active=True, starts_on__lte=today, ends_on__gte=today - timedelta(days=1))
    for c in comps:
        done = set(c.awards.values_list('affiliate_id', flat=True))
        for affiliate in Affiliate.objects.filter(status=Affiliate.Status.ACTIVE).exclude(pk__in=done):
            prog = progress(c, affiliate)
            if prog['reached'] and _award(c, affiliate, prog):
                awarded += 1
    return awarded


def competition_row(c: AffiliateCompetition, *, standings: bool = False) -> dict:
    row = {
        'id': c.id, 'name': c.name, 'description': c.description, 'starts_on': c.starts_on.isoformat(),
        'ends_on': c.ends_on.isoformat(), 'target_customers': c.target_customers, 'target_deposits': str(c.target_deposits),
        'min_customer_deposit': str(c.min_customer_deposit), 'prize': str(c.prize), 'active': c.active,
        'status': status_of(c), 'winners': c.awards.count(), 'paid_total': str((c.prize * c.awards.count()).quantize(CENT)),
        'created_by': c.created_by,
    }
    if standings:
        rows = []
        won = {a.affiliate_id: a for a in c.awards.all()}
        for affiliate in Affiliate.objects.filter(status=Affiliate.Status.ACTIVE).select_related():
            prog = progress(c, affiliate)
            if prog['customers'] or Decimal(prog['deposits']) > 0 or affiliate.pk in won:
                rows.append({'affiliate_id': affiliate.pk, 'code': affiliate.code, **prog,
                             'won': affiliate.pk in won})
        rows.sort(key=lambda r: (r['won'], r['percent'], Decimal(r['deposits'])), reverse=True)
        row['standings'] = rows[:100]
    return row


def for_agent(affiliate: Affiliate) -> list[dict]:
    """What an agent sees: running and upcoming competitions, and ones ended in
    the last 30 days, with their own progress and whether they've won."""
    today = timezone.localdate()
    won = {a.competition_id: a for a in affiliate.competition_awards.all()}
    out = []
    for c in AffiliateCompetition.objects.filter(active=True, ends_on__gte=today - timedelta(days=30)).order_by('ends_on'):
        out.append({**competition_row(c), 'my': progress(c, affiliate), 'won': c.id in won,
                    'won_at': won[c.id].awarded_at if c.id in won else None})
    return out


def _money(value, field: str) -> Decimal:
    try:
        return Decimal(str(value)).quantize(CENT)
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise CompetitionError(f'Enter the {field} as an amount.') from exc


def save(data: dict, *, by: str, competition: Optional[AffiliateCompetition] = None) -> AffiliateCompetition:
    c = competition or AffiliateCompetition()
    if 'name' in data or competition is None:
        c.name = str(data.get('name') or '').strip()[:80]
        if not c.name:
            raise CompetitionError('Give the competition a name.')
    if 'description' in data:
        c.description = str(data.get('description') or '').strip()[:300]
    for field in ('starts_on', 'ends_on'):
        if field in data or competition is None:
            try:
                setattr(c, field, date.fromisoformat(str(data.get(field))))
            except (TypeError, ValueError) as exc:
                raise CompetitionError('Enter the start and end dates.') from exc
    if c.ends_on < c.starts_on:
        raise CompetitionError('The end date is before the start date.')
    if 'target_customers' in data:
        try:
            c.target_customers = max(0, int(data.get('target_customers') or 0))
        except (TypeError, ValueError) as exc:
            raise CompetitionError('The customer target is a whole number.') from exc
    if 'target_deposits' in data:
        c.target_deposits = max(_money(data.get('target_deposits') or 0, 'deposit target'), ZERO)
    if 'min_customer_deposit' in data:
        c.min_customer_deposit = max(_money(data.get('min_customer_deposit') or 0, 'minimum deposit'), ZERO)
    if 'prize' in data or competition is None:
        c.prize = _money(data.get('prize'), 'prize')
        if c.prize <= 0:
            raise CompetitionError('The prize must be above zero.')
    if 'active' in data:
        c.active = bool(data['active'])
    if not c.target_customers and c.target_deposits <= 0:
        raise CompetitionError('Set a customer target, a deposit target, or both.')
    if competition is not None and competition.awards.exists() and any(
            k in data for k in ('target_customers', 'target_deposits', 'min_customer_deposit', 'prize', 'starts_on')):
        raise CompetitionError('Prizes were already paid for this competition: its targets and prize can’t change. '
                               'Switch it off and create a new one.')
    if competition is None:
        c.created_by = by[:150]
    c.save()
    accounts_services.audit(None, 'affiliate_competition_saved', None, competition=c.id, name=c.name, by=by,
                            prize=str(c.prize), customers=c.target_customers, deposits=str(c.target_deposits))
    return c


def adjust_locked(affiliate: Affiliate, amount, *, reason: str, by: str, request=None) -> Commission:
    """Add to (positive) or take from (negative) an agent's locked balance.
    Taking can't go below zero: at most what's locked now (or, when earnings
    aren't locked, what the agent has)."""
    from . import services
    amount = _money(amount, 'amount')
    if amount == 0:
        raise CompetitionError('Enter an amount to add (e.g. 10) or take away (e.g. -10).')
    reason = (reason or '').strip()
    if not reason:
        raise CompetitionError('Give a reason (the agent sees it).')
    with transaction.atomic():
        Affiliate.objects.select_for_update().filter(pk=affiliate.pk).first()
        if amount < 0:
            bal = services.balance(affiliate)
            from .models import AffiliateProgramme
            room = bal['locked'] if AffiliateProgramme.load().lock_until_month_end else bal['locked'] + bal['available']
            if -amount > room:
                raise CompetitionError(f'Only ${room:.2f} is locked: you can take at most that.')
        commission = Commission.objects.create(
            affiliate=affiliate, kind=Commission.Kind.ADJUST, amount=amount, base_amount=ZERO, rate=ZERO,
            status=Commission.Status.APPROVED, decided_at=timezone.now(), note=reason[:255])
    accounts_services.audit(affiliate.player_id, 'affiliate_balance_adjusted', request, amount=str(amount),
                            reason=reason, by=by)
    return commission

