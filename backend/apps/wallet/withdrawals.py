"""Player withdrawals: requested by the player, paid by staff.

Only the Winnings wallet can be withdrawn. Deposit and Bonus money never can
(a request naming either is refused and flagged — see WalletViolation); unplayed
deposits only go back through a staff refund (refund_deposit). A fee
(WithdrawalSettings.fee_percent, 5% by default) is kept from every withdrawal
and posted as its own `withdrawal_fee` ledger entry when the payout is made.

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
from .models import Bucket, LedgerEntry, PaymentTransaction, WithdrawalRequest, WithdrawalSettings

MOBILE = (WithdrawalRequest.Method.ECOCASH, WithdrawalRequest.Method.ONEMONEY, WithdrawalRequest.Method.INNBUCKS)
OPEN = WithdrawalRequest.Status.REQUESTED


class WithdrawalError(ValueError):
    """A request that can't go through; the message is for the player (or staff)."""

    def __init__(self, message: str, *, withdrawable=None, code: int = 400):
        super().__init__(message)
        self.withdrawable = withdrawable
        self.code = code


class WalletViolation(WithdrawalError):
    """An attempt to withdraw from the Deposit or Bonus wallet. The player app
    never offers this, so it means a hand-crafted request: callers record it."""

    def __init__(self, wallet: str):
        super().__init__('Only your Winnings wallet can be withdrawn. Deposit and Bonus money can be bet, '
                         'not withdrawn.', code=403)
        self.wallet = wallet


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
    """Only the Winnings wallet can be withdrawn."""
    return services.get_balances(player_id)[Bucket.WINNINGS]


def fee_for(amount: Decimal, cfg: WithdrawalSettings | None = None) -> Decimal:
    cfg = cfg or WithdrawalSettings.load()
    return (amount * cfg.fee_percent / Decimal('100')).quantize(Decimal('0.01'))


def turnover_left(player_id: int, cfg: WithdrawalSettings | None = None) -> Decimal:
    """How much more the player must bet before withdrawing: total stakes must
    reach min_turnover_percent of their deposits from before the three-wallet
    split (0 when met or the rule is off). That money was moved into Winnings,
    so this keeps it from being withdrawn unplayed; newer deposits sit in the
    Deposit wallet, which can't be withdrawn at all."""
    cfg = cfg or WithdrawalSettings.load()
    if not cfg.min_turnover_percent:
        return Decimal('0')
    deposits = LedgerEntry.objects.filter(
        wallet__player_id=player_id, kind='deposit', legacy=True,
    ).aggregate(t=Sum('amount'))['t'] or Decimal('0')
    if deposits <= 0:
        return Decimal('0')
    totals = {r['kind']: r['t'] for r in LedgerEntry.objects.filter(
        wallet__player_id=player_id, kind__in=('bet_stake', 'casino_debit'),
    ).values('kind').annotate(t=Sum('amount'))}
    staked = -((totals.get('bet_stake') or Decimal('0')) + (totals.get('casino_debit') or Decimal('0')))
    needed = (deposits * cfg.min_turnover_percent / 100).quantize(Decimal('0.01'))
    return max(needed - staked, Decimal('0'))


def requested_today(player_id: int, now=None) -> Decimal:
    now = now or timezone.now()
    start = timezone.localtime(now).replace(hour=0, minute=0, second=0, microsecond=0)
    total = (WithdrawalRequest.objects.filter(player_id=player_id, created_at__gte=start)
             .exclude(status__in=(WithdrawalRequest.Status.REJECTED, WithdrawalRequest.Status.CANCELLED))
             .aggregate(t=Sum('amount'))['t'])
    return total or Decimal('0')


@transaction.atomic
def request(*, player, amount, method: str, account_number: str = '', account_name: str = '',
            bank_name: str = '', now=None, wallet: str | None = None) -> WithdrawalRequest:
    """Ask to be paid out of the Winnings wallet. Raises WithdrawalError
    (WalletViolation for any other wallet) or services.InsufficientFunds."""
    if wallet not in (None, '', Bucket.WINNINGS):
        raise WalletViolation(str(wallet)[:20])
    now = now or timezone.now()
    # AML/KYC: nothing leaves the platform until identity is verified. (Self-
    # exclusion deliberately doesn't block withdrawals — players can always
    # take their winnings; unplayed deposits come back via refund_deposit.)
    if player.kyc_status != player.Kyc.VERIFIED:
        raise WithdrawalError('Identity verification is required before you can withdraw.', code=403)
    from apps.risk import services as risk
    blocked = risk.withdrawals_blocked(player)
    if blocked:
        raise WithdrawalError(blocked, code=403)
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
        raise WithdrawalError(
            f'You can withdraw up to ${available:.2f} — only your Winnings wallet can be withdrawn.',
            withdrawable=available, code=402)
    left = turnover_left(player.id, cfg)
    if left > 0:
        raise WithdrawalError(
            f'Withdrawals open once you’ve played your deposits — bet ${left:.2f} more first '
            f'(sports or Aviator).', code=403)

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

    fee = fee_for(amount, cfg)
    held = risk.needs_review(player.id)
    req = WithdrawalRequest.objects.create(
        risk_hold=held, risk_note='Account under fraud review' if held else '',
        player_id=player.id, amount=amount, fee=fee, method=method, account_number=number[:60],
        account_name=(account_name or '').strip()[:120], bank_name=(bank_name or '').strip()[:80] if method == 'bank' else '',
    )
    services.debit(player_id=player.id, amount=amount, kind=LedgerEntry.Kind.WITHDRAWAL_HOLD,
                   idempotency_key=f'withdrawal:{req.id}:hold', reference=f'withdrawal:{req.id}')
    # May hold this request (or freeze the account) if it looks wrong.
    risk.on_withdrawal_request(req)
    _notify(player.id, 'Withdrawal requested',
            f'We’ve received your request for ${amount:.2f} to {req.get_method_display()}. '
            f'You’ll be sent ${req.payout_amount:.2f} after the ${fee:.2f} withdrawal fee, '
            'and notified as soon as it’s sent.')
    return req


def _locked(req_id: int) -> WithdrawalRequest:
    req = WithdrawalRequest.objects.select_for_update().filter(pk=req_id).first()
    if req is None:
        raise WithdrawalError('Withdrawal not found.', code=404)
    return req


def _give_back(req: WithdrawalRequest, why: str) -> None:
    """Return the money to the balance. A legacy request was already posted
    as a withdrawal, so it's reversed as one (reports net it out)."""
    if req.legacy:
        services.credit(player_id=req.player_id, amount=req.amount, kind=LedgerEntry.Kind.WITHDRAWAL,
                        idempotency_key=f'withdrawal:{req.id}:legacy-return', reference=f'withdrawal:{req.id}:{why}')
    else:
        _return_hold(req, why)


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
    _give_back(req, 'cancelled')
    req.status, req.decided_at = WithdrawalRequest.Status.CANCELLED, now or timezone.now()
    req.save(update_fields=['status', 'decided_at'])
    return req


@transaction.atomic
def mark_paid(req_id: int, *, reference: str, by: str = '', confirm_amount=None, now=None) -> WithdrawalRequest:
    """Staff sent the money: record the reference and post the withdrawal.
    `confirm_amount` (when given — the console always sends it) must match
    what was to be sent (the request less its fee), so a stale screen or a
    slip can't mark the wrong one paid."""
    reference = (reference or '').strip()
    if len(reference) < 3:
        raise WithdrawalError('Enter the EcoCash/bank transaction reference.')
    req = _locked(req_id)
    if confirm_amount is not None:
        try:
            typed = Decimal(str(confirm_amount)).quantize(Decimal('0.01'))
        except (InvalidOperation, ValueError, TypeError):
            typed = None
        if typed != req.payout_amount:
            raise WithdrawalError(f'The amount you confirmed doesn’t match what was to be sent (${req.payout_amount:.2f}).')
    if req.status != OPEN:
        raise WithdrawalError(f'This withdrawal is already {req.get_status_display().lower()}.', code=409)
    if req.risk_hold:
        raise WithdrawalError('This withdrawal is held by a fraud check — review the player’s case first '
                              f'({req.risk_note or "Fraud & risk"}).', code=409)
    # Release the hold and post what was sent plus the fee kept — balance
    # unchanged, and reports now count the money out and the fee earned.
    # (A legacy one was posted long ago.)
    if not req.legacy:
        _return_hold(req, 'paid')
        services.debit(player_id=req.player_id, amount=req.payout_amount, kind=LedgerEntry.Kind.WITHDRAWAL,
                       idempotency_key=f'withdrawal:{req.id}:paid', reference=f'withdrawal:{req.id}:{reference}'[:200])
        if req.fee > 0:
            services.debit(player_id=req.player_id, amount=req.fee, kind=LedgerEntry.Kind.WITHDRAWAL_FEE,
                           idempotency_key=f'withdrawal:{req.id}:fee', reference=f'withdrawal:{req.id}:fee')
    req.status, req.reference = WithdrawalRequest.Status.PAID, reference[:120]
    req.decided_by, req.decided_at = by[:150], now or timezone.now()
    req.save(update_fields=['status', 'reference', 'decided_by', 'decided_at'])
    where = 'you' if req.legacy else f'your {req.get_method_display()} ({_tail(req.account_number)})'
    _notify(req.player_id, 'Withdrawal sent', f'${req.payout_amount:.2f} has been sent to {where}. Reference: {reference}.')
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
    _give_back(req, 'rejected')
    req.status, req.note = WithdrawalRequest.Status.REJECTED, note[:300]
    req.decided_by, req.decided_at = by[:150], now or timezone.now()
    req.save(update_fields=['status', 'note', 'decided_by', 'decided_at'])
    _notify(req.player_id, 'Withdrawal not sent',
            f'Your ${req.amount:.2f} withdrawal was declined and the money is back in your Winnings wallet. Reason: {note}')
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
    balances = services.get_balances(player_id)
    return {
        'balance': m(services.get_balance(player_id)),
        'deposit_balance': m(balances[Bucket.DEPOSIT]), 'bonus_balance': m(balances[Bucket.BONUS]),
        'winnings_balance': m(balances[Bucket.WINNINGS]),
        'deposits': m(deposits), 'paid_out': m(paid_out), 'net': m(deposits - paid_out),
        'pending': m(WithdrawalRequest.objects.filter(player_id=player_id, status=OPEN).aggregate(t=Sum('amount'))['t']),
        'bonus_locked': m(promotions_services.bonus_status(player_id)['locked']),
        'big_wins_7d': [{**w, 'amount': m(w['amount']), 'created_at': w['created_at'].isoformat()} for w in big],
    }


def payload(req: WithdrawalRequest, *, staff: bool = False) -> dict:
    data = {
        'id': req.id, 'amount': str(req.amount), 'fee': str(req.fee), 'payout_amount': str(req.payout_amount),
        'method': req.method, 'method_label': req.get_method_display(),
        'account_number': req.account_number if staff else _tail(req.account_number),
        'account_name': req.account_name, 'bank_name': req.bank_name,
        'status': req.status, 'status_label': req.get_status_display(),
        'reference': req.reference, 'note': req.note,
        'created_at': req.created_at.isoformat(), 'decided_at': req.decided_at.isoformat() if req.decided_at else None,
        'legacy': req.legacy,
    }
    if staff:
        data.update(risk_hold=req.risk_hold, risk_note=req.risk_note)
    if staff:
        data.update(player_id=req.player_id, decided_by=req.decided_by)
    return data


# -- staff refund of unplayed deposits ---------------------------------------

REFUND_REASONS = {'self_exclusion': 'Self-exclusion', 'account_closure': 'Account closure'}


def refund_destinations(player_id: int) -> list[str]:
    """The mobile numbers this player's completed deposits came from — the
    only places a deposit refund may be sent."""
    return sorted(set(PaymentTransaction.objects.filter(
        player_id=player_id, status=PaymentTransaction.Status.PAID,
    ).exclude(phone='').values_list('phone', flat=True)))


@transaction.atomic
def refund_deposit(*, player, amount, reason: str, destination: str, reference: str, by: str) -> LedgerEntry:
    """Return unplayed Deposit-wallet money (staff only) when a player
    self-excludes or their account is closed (suspended first). Only to a
    number their deposits came from, and only after staff have sent it —
    `reference` is the EcoCash/bank transaction reference."""
    if reason not in REFUND_REASONS:
        raise WithdrawalError('A deposit refund is only for self-exclusion or account closure.')
    if reason == 'self_exclusion' and not player.self_excluded:
        raise WithdrawalError('This player isn’t self-excluded.')
    if reason == 'account_closure' and not player.is_suspended:
        raise WithdrawalError('Suspend the account before refunding its deposits for closure.')
    reference = (reference or '').strip()
    if len(reference) < 3:
        raise WithdrawalError('Enter the EcoCash/bank transaction reference of the refund you sent.')
    if destination not in refund_destinations(player.id):
        raise WithdrawalError('Deposits can only be refunded to a number they were paid from.', code=403)
    amount = _money(amount)
    return services.debit(
        player_id=player.id, amount=amount, kind=LedgerEntry.Kind.DEPOSIT_REFUND,
        idempotency_key=f'deposit-refund:{player.id}:{reference}'[:200],
        reference=f'deposit-refund:{reason}:{destination}:{reference}:{by}'[:200],
    )
