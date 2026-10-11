"""Player withdrawals: requested by the player, paid by staff.

Payouts aren't automatic. When a player asks, the amount is held off their
balance (`withdrawal_hold`) so it can't be bet or asked for twice. Staff send
the money themselves (EcoCash, OneMoney, InnBucks, bank) and mark the request
paid with the transaction reference — only then does it post as a
`withdrawal`, which is what reports count. Rejecting (or the player
cancelling) returns the hold to the balance.
"""
from __future__ import annotations

import re
from datetime import timedelta
from decimal import Decimal, InvalidOperation

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from . import services
from .models import LedgerEntry, WithdrawalRequest, WithdrawalSettings

MOBILE = (WithdrawalRequest.Method.ECOCASH, WithdrawalRequest.Method.ONEMONEY, WithdrawalRequest.Method.INNBUCKS)
OPEN = WithdrawalRequest.Status.REQUESTED


class WithdrawalError(ValueError):
    """A request that can't go through; the message is for the player (or staff)."""

    def __init__(self, message: str, *, withdrawable=None, code: int = 400):
        super().__init__(message)
        self.withdrawable = withdrawable
        self.code = code


def _notify(player_id: int, title: str, body: str) -> None:
    from apps.notifications import services as notif_services
    notif_services.notify(player_id=player_id, kind='account_alert', title=title, body=body)


def _money(value) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError, TypeError):
        raise WithdrawalError('Enter a valid amount.')
    if amount <= 0:
        raise WithdrawalError('Enter an amount above zero.')
    return amount


def withdrawable(player_id: int) -> Decimal:
    from apps.promotions import services as promotions_services
    locked = promotions_services.bonus_status(player_id)['locked']
    return max(services.get_balance(player_id) - locked, Decimal('0'))


def requested_today(player_id: int, now=None) -> Decimal:
    now = now or timezone.now()
    start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    total = (WithdrawalRequest.objects.filter(player_id=player_id, created_at__gte=start)
             .exclude(status__in=(WithdrawalRequest.Status.REJECTED, WithdrawalRequest.Status.CANCELLED))
             .aggregate(t=Sum('amount'))['t'])
    return total or Decimal('0')


@transaction.atomic
def request(*, player, amount, method: str, account_number: str = '', account_name: str = '',
            bank_name: str = '', now=None) -> WithdrawalRequest:
    """Ask to be paid out. Raises WithdrawalError or services.InsufficientFunds."""
    now = now or timezone.now()
    # AML/KYC: nothing leaves the platform until identity is verified. (Self-
    # exclusion deliberately doesn't block withdrawals — players can always
    # get their own money back.)
    if player.kyc_status != player.Kyc.VERIFIED:
        raise WithdrawalError('Identity verification is required before you can withdraw.', code=403)
    amount = _money(amount)
    cfg = WithdrawalSettings.load()
    if amount < cfg.min_amount:
        raise WithdrawalError(f'The minimum withdrawal is ${cfg.min_amount:.2f}.')
    if amount > cfg.max_amount:
        raise WithdrawalError(f'The most you can withdraw at once is ${cfg.max_amount:.2f}.')
    if cfg.daily_max and requested_today(player.id, now) + amount > cfg.daily_max:
        left = max(cfg.daily_max - requested_today(player.id, now), Decimal('0'))
        raise WithdrawalError(f'You can withdraw up to ${cfg.daily_max:.2f} a day — ${left:.2f} left today.')
    available = withdrawable(player.id)
    if amount > available:
        from apps.promotions import services as promotions_services
        bonus = promotions_services.bonus_status(player.id)
        if bonus['locked'] > 0:
            raise WithdrawalError(
                f"{bonus['locked']} of your balance is bonus money — bet {bonus['wagering_remaining']} more to "
                f'unlock it. You can withdraw up to {available} now.', withdrawable=available, code=403)
        raise services.InsufficientFunds(f'You can withdraw up to {available}.')

    if method not in WithdrawalRequest.Method.values:
        raise WithdrawalError('Choose where to send the money: EcoCash, OneMoney, InnBucks or bank.')
    if method in MOBILE:
        number = re.sub(r'[^0-9+]', '', account_number or '')
        if not re.fullmatch(r'\+?\d{9,13}', number):
            raise WithdrawalError('Enter the mobile number to send the money to.')
    else:
        number = (account_number or '').strip()
        if len(number) < 5 or not (bank_name or '').strip() or not (account_name or '').strip():
            raise WithdrawalError('Enter the bank, account name and account number.')

    req = WithdrawalRequest.objects.create(
        player_id=player.id, amount=amount, method=method, account_number=number[:60],
        account_name=(account_name or '').strip()[:120], bank_name=(bank_name or '').strip()[:80] if method == 'bank' else '',
    )
    services.debit(player_id=player.id, amount=amount, kind=LedgerEntry.Kind.WITHDRAWAL_HOLD,
                   idempotency_key=f'withdrawal:{req.id}:hold', reference=f'withdrawal:{req.id}')
    _notify(player.id, 'Withdrawal requested',
            f'We’ve received your request for ${amount:.2f} to {req.get_method_display()}. '
            'You’ll be notified as soon as it’s sent.')
    return req


def _locked(req_id: int) -> WithdrawalRequest:
    req = WithdrawalRequest.objects.select_for_update().filter(pk=req_id).first()
    if req is None:
        raise WithdrawalError('Withdrawal not found.', code=404)
    return req


def _return_hold(req: WithdrawalRequest, why: str) -> None:
    services.credit(player_id=req.player_id, amount=req.amount, kind=LedgerEntry.Kind.WITHDRAWAL_HOLD,
                    idempotency_key=f'withdrawal:{req.id}:return', reference=f'withdrawal:{req.id}:{why}')


@transaction.atomic
def cancel(*, player_id: int, req_id: int, now=None) -> WithdrawalRequest:
    """The player changes their mind before it's paid: the money goes back."""
    req = _locked(req_id)
    if req.player_id != player_id:
        raise WithdrawalError('Withdrawal not found.', code=404)
    if req.status != OPEN:
        raise WithdrawalError('This withdrawal has already been handled.', code=409)
    _return_hold(req, 'cancelled')
    req.status, req.decided_at = WithdrawalRequest.Status.CANCELLED, now or timezone.now()
    req.save(update_fields=['status', 'decided_at'])
    return req


@transaction.atomic
def mark_paid(req_id: int, *, reference: str, by: str = '', now=None) -> WithdrawalRequest:
    """Staff sent the money: record the reference and post the withdrawal."""
    reference = (reference or '').strip()
    if len(reference) < 3:
        raise WithdrawalError('Enter the EcoCash/bank transaction reference.')
    req = _locked(req_id)
    if req.status != OPEN:
        raise WithdrawalError(f'This withdrawal is already {req.get_status_display().lower()}.', code=409)
    # Release the hold and post the real withdrawal — balance unchanged, and
    # reports now count it as money out.
    _return_hold(req, 'paid')
    services.debit(player_id=req.player_id, amount=req.amount, kind=LedgerEntry.Kind.WITHDRAWAL,
                   idempotency_key=f'withdrawal:{req.id}:paid', reference=f'withdrawal:{req.id}:{reference}'[:200])
    req.status, req.reference = WithdrawalRequest.Status.PAID, reference[:120]
    req.decided_by, req.decided_at = by[:150], now or timezone.now()
    req.save(update_fields=['status', 'reference', 'decided_by', 'decided_at'])
    _notify(req.player_id, 'Withdrawal sent',
            f'${req.amount:.2f} has been sent to your {req.get_method_display()} ({_tail(req.account_number)}). '
            f'Reference: {reference}.')
    return req


@transaction.atomic
def reject(req_id: int, *, note: str, by: str = '', now=None) -> WithdrawalRequest:
    """Staff decline it (e.g. details don't match): the money goes back to the balance."""
    note = (note or '').strip()
    if len(note) < 3:
        raise WithdrawalError('Say why it’s being rejected — the player sees this.')
    req = _locked(req_id)
    if req.status != OPEN:
        raise WithdrawalError(f'This withdrawal is already {req.get_status_display().lower()}.', code=409)
    _return_hold(req, 'rejected')
    req.status, req.note = WithdrawalRequest.Status.REJECTED, note[:300]
    req.decided_by, req.decided_at = by[:150], now or timezone.now()
    req.save(update_fields=['status', 'note', 'decided_by', 'decided_at'])
    _notify(req.player_id, 'Withdrawal not sent',
            f'Your ${req.amount:.2f} withdrawal was declined and the money is back in your balance. Reason: {note}')
    return req


def _tail(number: str) -> str:
    return f'••{number[-4:]}' if len(number) > 4 else number


def player_context(player_id: int) -> dict:
    """What staff check before paying: money in vs out, bonus, recent big wins."""
    from apps.promotions import services as promotions_services
    entries = LedgerEntry.objects.filter(wallet__player_id=player_id)
    totals = {r['kind']: r['t'] for r in entries.values('kind').annotate(t=Sum('amount'))}
    deposits = totals.get('deposit') or Decimal('0')
    paid_out = -(totals.get('withdrawal') or Decimal('0'))
    since = timezone.now() - timedelta(days=7)
    big = (entries.filter(kind__in=('bet_payout', 'casino_credit'), created_at__gte=since)
           .order_by('-amount').values('amount', 'kind', 'created_at', 'reference')[:3])
    def m(v) -> str:
        return f'{(v or Decimal("0")):.2f}'
    return {
        'balance': m(services.get_balance(player_id)),
        'deposits': m(deposits), 'paid_out': m(paid_out), 'net': m(deposits - paid_out),
        'pending': m(WithdrawalRequest.objects.filter(player_id=player_id, status=OPEN).aggregate(t=Sum('amount'))['t']),
        'bonus_locked': m(promotions_services.bonus_status(player_id)['locked']),
        'big_wins_7d': [{**w, 'amount': m(w['amount']), 'created_at': w['created_at'].isoformat()} for w in big],
    }


def payload(req: WithdrawalRequest, *, staff: bool = False) -> dict:
    data = {
        'id': req.id, 'amount': str(req.amount), 'method': req.method, 'method_label': req.get_method_display(),
        'account_number': req.account_number if staff else _tail(req.account_number),
        'account_name': req.account_name, 'bank_name': req.bank_name,
        'status': req.status, 'status_label': req.get_status_display(),
        'reference': req.reference, 'note': req.note,
        'created_at': req.created_at.isoformat(), 'decided_at': req.decided_at.isoformat() if req.decided_at else None,
    }
    if staff:
        data.update(player_id=req.player_id, decided_by=req.decided_by)
    return data
