"""House revenue share — the only place its books change (see models.py).

Every completed day is closed once: its real-money GGR (see day_ggr) has any loss still carried from
earlier losing days netted off first; each of the three wallets is credited
its share of what's left and the operating pool keeps the rest. Days close in
order, by an hourly job and whenever the page is opened, so nothing is missed.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Optional

from django.db import IntegrityError, transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts import services as accounts_services

from .models import PoolExpense, RevenueDay, RevenueSettings, ShareEntry, ShareWallet, ShareWithdrawal

CENT = Decimal('0.01')
ZERO = Decimal('0.00')


class RevenueError(ValueError):
    """Something staff asked for that the rules don't allow (shown to them)."""


def _aware(day: date) -> datetime:
    return timezone.make_aware(datetime.combine(day, time.min))


def _sum(qs, field='amount') -> Decimal:
    return (qs.aggregate(v=Sum(field))['v'] or ZERO).quantize(CENT)


CASH_STAKES = ('bet_stake', 'casino_debit')
CASH_WINS = ('bet_payout', 'casino_credit', 'bet_reversal')  # a reversal is negative: winnings taken back


def real_money(start: datetime, end: datetime) -> dict:
    """Revenue in real money only, from the player ledger. Bonus money is not
    money until a player turns it into Winnings, so stakes and wins on the Bonus
    wallet are left out; the moment bonus money is converted into withdrawable
    Winnings it counts as a cost. Bonus credits and forfeits never count."""
    from apps.wallet.models import Bucket, LedgerEntry
    cash = (Bucket.DEPOSIT, Bucket.WINNINGS)
    qs = LedgerEntry.objects.filter(created_at__gte=start, created_at__lt=end)
    stakes = -_sum(qs.filter(kind__in=CASH_STAKES, bucket__in=cash))
    wins = _sum(qs.filter(kind__in=CASH_WINS, bucket__in=cash))
    conversions = _sum(qs.filter(kind='bonus_conversion', bucket=Bucket.WINNINGS))
    return {'stakes': stakes, 'wins': wins, 'bonus_conversions': conversions, 'ggr': stakes - wins - conversions}


def day_ggr(day: date) -> Decimal:
    """The day's real-money GGR: cash stakes minus cash wins, less bonus money
    converted into Winnings that day."""
    return real_money(_aware(day), _aware(day + timedelta(days=1)))['ggr']


def day_bonus_conversions(day: date) -> Decimal:
    return real_money(_aware(day), _aware(day + timedelta(days=1)))['bonus_conversions']


def day_affiliate_costs(day: date) -> Decimal:
    """Affiliate commissions that became final that day."""
    from apps.affiliates.models import Commission
    return _sum(Commission.objects.filter(status__in=(Commission.Status.APPROVED, Commission.Status.PAID),
                                          decided_at__gte=_aware(day), decided_at__lt=_aware(day + timedelta(days=1))))


def split(ggr: Decimal, carried_in: Decimal, percent: Decimal, wallets: int = 3) -> dict:
    """One day's maths. A loss carried from earlier days is netted off first;
    a day that ends below zero shares nothing and carries the rest forward.
    Shares are rounded down to the cent; the pool keeps the remainder."""
    net = ggr + carried_in
    base = max(net, ZERO)
    share_each = (base * percent / Decimal('100')).quantize(CENT, rounding=ROUND_DOWN)
    return {'base': base, 'carry_out': min(net, ZERO), 'share_each': share_each, 'pool': base - share_each * wallets}


def close_days(*, today: Optional[date] = None) -> int:
    """Close every completed day not yet closed, oldest first (the carry needs
    the order). Idempotent, and serialised on the settings row so two runs can't
    close the same day. Returns how many days were closed."""
    today = today or timezone.localdate()
    closed = 0
    with transaction.atomic():
        cfg = RevenueSettings.objects.select_for_update().get(pk=RevenueSettings.load().pk)
        if cfg.started_on is None or cfg.started_on >= today:
            return 0
        wallets = ShareWallet.ensure()
        last = RevenueDay.objects.order_by('-day').first()
        day = max(cfg.started_on, last.day + timedelta(days=1)) if last else cfg.started_on
        carried = last.carry_out if last else ZERO
        while day < today:
            ggr = day_ggr(day)
            maths = split(ggr, carried, cfg.share_percent, len(wallets))
            record = RevenueDay.objects.create(
                day=day, ggr=ggr, carried_in=carried, share_percent=cfg.share_percent,
                bonus_conversions=day_bonus_conversions(day), affiliate_costs=day_affiliate_costs(day), **maths,
            )
            if maths['share_each'] > 0:
                ShareEntry.objects.bulk_create([
                    ShareEntry(wallet=w, kind=ShareEntry.Kind.ACCRUAL, amount=maths['share_each'], day=record) for w in wallets
                ])
            carried = maths['carry_out']
            day += timedelta(days=1)
            closed += 1
    return closed


# -- wallets ----------------------------------------------------------------------

def wallet_balance(wallet: ShareWallet) -> Decimal:
    return _sum(wallet.entries.all())


def wallet_summary(wallet: ShareWallet, *, entries: int = 20) -> dict:
    open_request = wallet.withdrawals.filter(status=ShareWithdrawal.Status.REQUESTED).first()
    return {
        'slot': wallet.slot, 'label': wallet.label or f'Partner {wallet.slot}',
        'holder_id': wallet.holder_id, 'holder': wallet.holder.get_username() if wallet.holder else None,
        'balance': str(wallet_balance(wallet)),
        'earned_total': str(_sum(wallet.entries.filter(kind=ShareEntry.Kind.ACCRUAL))),
        'paid_total': str(_sum(wallet.withdrawals.filter(status=ShareWithdrawal.Status.PAID))),
        'open_withdrawal': withdrawal_row(open_request) if open_request else None,
        'entries': [{'kind': e.kind, 'label': e.get_kind_display(), 'amount': str(e.amount),
                     'day': e.day.day.isoformat() if e.day_id else None, 'at': e.created_at.isoformat()}
                    for e in wallet.entries.select_related('day')[:entries]],
    }


def withdrawal_row(w: ShareWithdrawal) -> dict:
    return {'id': w.id, 'slot': w.wallet.slot, 'label': w.wallet.label or f'Partner {w.wallet.slot}',
            'amount': str(w.amount), 'status': w.status, 'status_label': w.get_status_display(),
            'method': w.method, 'method_label': w.get_method_display(), 'account': w.account,
            'reference': w.reference, 'note': w.note, 'requested_by': w.requested_by, 'decided_by': w.decided_by,
            'created_at': w.created_at.isoformat(), 'decided_at': w.decided_at.isoformat() if w.decided_at else None}


@transaction.atomic
def request_withdrawal(*, user, method: str, account: str = '', request=None) -> ShareWithdrawal:
    """The holder asks for their whole balance; the wallet resets to zero at once."""
    wallet = ShareWallet.objects.select_for_update().filter(holder=user).first()
    if wallet is None:
        raise RevenueError('You don’t hold a revenue-share wallet.')
    from .audit import assert_unlocked
    assert_unlocked()
    if method not in ShareWithdrawal.Method.values:
        raise RevenueError('Choose how you want to be paid.')
    account = (account or '').strip()[:120]
    if method != ShareWithdrawal.Method.CASH and len(account) < 5:
        raise RevenueError('Enter the number or account to pay.')
    if wallet.withdrawals.filter(status=ShareWithdrawal.Status.REQUESTED).exists():
        raise RevenueError('You already have a withdrawal waiting to be paid.')
    amount = wallet_balance(wallet)
    if amount < CENT:
        raise RevenueError('There is nothing to withdraw yet.')
    try:
        withdrawal = ShareWithdrawal.objects.create(wallet=wallet, amount=amount, method=method, account=account,
                                                    requested_by=user.get_username())
    except IntegrityError as exc:  # a second request raced this one
        raise RevenueError('You already have a withdrawal waiting to be paid.') from exc
    ShareEntry.objects.create(wallet=wallet, kind=ShareEntry.Kind.WITHDRAWAL, amount=-amount, withdrawal=withdrawal)
    accounts_services.audit(None, 'revenue_withdrawal_requested', request, slot=wallet.slot, amount=str(amount),
                            method=method, by=user.get_username())
    return withdrawal


@transaction.atomic
def decide_withdrawal(withdrawal_id: int, *, decision: str, by: str, reference: str = '', note: str = '',
                      request=None) -> ShareWithdrawal:
    """A superuser records the money as sent (paid) or declines it (the amount
    goes back into the wallet)."""
    withdrawal = ShareWithdrawal.objects.select_for_update().select_related('wallet').filter(pk=withdrawal_id).first()
    if withdrawal is None:
        raise RevenueError('Withdrawal not found.')
    if withdrawal.status != ShareWithdrawal.Status.REQUESTED:
        raise RevenueError(f'This withdrawal is already {withdrawal.get_status_display().lower()}.')
    if decision not in ('paid', 'rejected'):
        raise RevenueError('Choose paid or rejected.')
    if decision == 'paid':              # rejecting (money back to the wallet) stays open
        from .audit import assert_unlocked
        assert_unlocked()
    withdrawal.status = decision
    withdrawal.reference = (reference or '').strip()[:100]
    withdrawal.note = (note or '').strip()[:500]
    withdrawal.decided_by = by[:150]
    withdrawal.decided_at = timezone.now()
    withdrawal.save(update_fields=['status', 'reference', 'note', 'decided_by', 'decided_at'])
    if decision == 'rejected':
        ShareEntry.objects.create(wallet=withdrawal.wallet, kind=ShareEntry.Kind.RETURN, amount=withdrawal.amount,
                                  withdrawal=withdrawal)
    accounts_services.audit(None, f'revenue_withdrawal_{decision}', request, slot=withdrawal.wallet.slot,
                            amount=str(withdrawal.amount), reference=withdrawal.reference, by=by)
    return withdrawal


# -- pool -------------------------------------------------------------------------

def pool_summary() -> dict:
    """The operating pool: its share of every closed day, less affiliate
    commissions and the costs staff recorded."""
    days = RevenueDay.objects.all()
    earned, affiliates, expenses = _sum(days, 'pool'), _sum(days, 'affiliate_costs'), _sum(PoolExpense.objects.all())
    by_category = {c: str((v or ZERO).quantize(CENT)) for c, v in PoolExpense.objects.values_list('category').annotate(t=Sum('amount'))}
    return {'earned': str(earned), 'affiliate_costs': str(affiliates), 'expenses': str(expenses),
            'remaining': str(earned - affiliates - expenses), 'expenses_by_category': by_category}


def record_expense(*, day, category: str, amount, note: str = '', by: str, request=None) -> PoolExpense:
    if category not in PoolExpense.Category.values:
        raise RevenueError('Choose a category.')
    try:
        amount = Decimal(str(amount)).quantize(CENT)
        day = date.fromisoformat(str(day)) if not isinstance(day, date) else day
    except (ArithmeticError, ValueError) as exc:
        raise RevenueError('Enter a date and an amount.') from exc
    if amount <= 0:
        raise RevenueError('The amount must be above zero.')
    if day > timezone.localdate():
        raise RevenueError('That date is in the future.')
    from .audit import assert_unlocked, locked
    assert_unlocked()
    if locked(day):
        raise RevenueError('That week is approved by every partner — its costs are locked. Record it in the current week instead.')
    expense = PoolExpense.objects.create(day=day, category=category, amount=amount, note=(note or '').strip()[:300],
                                         recorded_by=by[:150])
    accounts_services.audit(None, 'revenue_expense_recorded', request, category=category, amount=str(amount),
                            day=day.isoformat(), note=expense.note, by=by)
    return expense


def delete_expense(expense_id: int, *, by: str, request=None) -> None:
    expense = PoolExpense.objects.filter(pk=expense_id).first()
    if expense is None:
        raise RevenueError('Expense not found.')
    from .audit import assert_unlocked, locked
    assert_unlocked()
    if locked(expense.day):
        raise RevenueError('That week is approved by every partner — its costs are locked.')
    if hasattr(expense, 'proposal'):
        raise RevenueError('That was agreed by every partner and can’t be deleted.')
    accounts_services.audit(None, 'revenue_expense_deleted', request, category=expense.category,
                            amount=str(expense.amount), day=expense.day.isoformat(), by=by)
    expense.delete()


# -- settings ---------------------------------------------------------------------

def update_settings(*, share_percent=None, started_on=None, wallets=None, founder_id=..., by: str,
                    request=None) -> RevenueSettings:
    """Superuser: the share per wallet (applies to days not yet closed), the
    first day that counts (only before any day has closed), and who holds each
    wallet (a staff login; one wallet each)."""
    from django.contrib.auth import get_user_model

    from .audit import assert_unlocked
    assert_unlocked()
    with transaction.atomic():
        cfg = RevenueSettings.objects.select_for_update().get(pk=RevenueSettings.load().pk)
        if share_percent is not None:
            try:
                pct = Decimal(str(share_percent)).quantize(CENT)
            except ArithmeticError as exc:
                raise RevenueError('Enter the share as a number.') from exc
            if not Decimal('0') <= pct <= Decimal('33.33'):
                raise RevenueError('Each wallet’s share must be between 0% and 33.33% (three wallets).')
            cfg.share_percent = pct
        if started_on is not None and str(started_on) != str(cfg.started_on):
            if RevenueDay.objects.exists():
                raise RevenueError('The start date can’t change once days have been shared.')
            try:
                start = date.fromisoformat(str(started_on))
            except ValueError as exc:
                raise RevenueError('Enter the start date as YYYY-MM-DD.') from exc
            if start > timezone.localdate():
                raise RevenueError('The start date can’t be in the future.')
            cfg.started_on = start
        if founder_id is not ...:
            if founder_id in (None, ''):
                cfg.founder = None
            else:
                user = get_user_model().objects.filter(pk=founder_id, is_superuser=True, is_active=True).first()
                if user is None:
                    raise RevenueError('The founder must be an active superuser.')
                cfg.founder = user
        cfg.save()
        if wallets:
            ShareWallet.ensure()
            users = get_user_model().objects
            for row in wallets:
                wallet = ShareWallet.objects.select_for_update().filter(slot=row.get('slot')).first()
                if wallet is None:
                    raise RevenueError('Unknown wallet.')
                if 'label' in row:
                    wallet.label = str(row.get('label') or '').strip()[:60]
                if 'holder_id' in row:
                    holder_id = row.get('holder_id')
                    if holder_id in (None, ''):
                        wallet.holder = None
                    else:
                        user = users.filter(pk=holder_id, is_staff=True, is_active=True).first()
                        if user is None:
                            raise RevenueError('A wallet holder must be an active staff login.')
                        clash = ShareWallet.objects.filter(holder=user).exclude(pk=wallet.pk).first()
                        if clash is not None:
                            raise RevenueError(f'{user.get_username()} already holds Partner {clash.slot}’s wallet.')
                        wallet.holder = user
                wallet.save()
    accounts_services.audit(None, 'revenue_settings', request, share_percent=str(cfg.share_percent),
                            started_on=str(cfg.started_on), by=by,
                            founder=cfg.founder.get_username() if cfg.founder else None,
                            holders={w.slot: (w.holder.get_username() if w.holder else None) for w in ShareWallet.ensure()})
    return cfg


def today_so_far() -> dict:
    """Today's GGR so far and what each wallet would get if the day ended now."""
    cfg = RevenueSettings.load()
    today = timezone.localdate()
    figures = real_money(_aware(today), timezone.now())
    ggr = figures['ggr']
    last = RevenueDay.objects.order_by('-day').first()
    maths = split(ggr, last.carry_out if last else ZERO, cfg.share_percent)
    return {'day': today.isoformat(), 'ggr': str(ggr), 'bonus_conversions': str(figures['bonus_conversions']),
            'carried_in': str(last.carry_out if last else ZERO),
            **{k: str(v) for k, v in maths.items()}}
