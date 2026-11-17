"""What the business owes right now: players, agents (affiliates) and revenue-share
partners. Read-only, from the same balances the rest of the admin uses.

* Players: Winnings and Deposit balances (withdrawable; Deposit at its higher
  fee), plus withdrawals requested but not yet sent (the money already left the
  wallets). Bonus money and unclaimed Aviator bonus profit are shown apart:
  they're promotional, not cash owed, until a player turns them into Winnings.
* Agents: approved commissions not yet paid out (available + locked until month
  end) and payouts requested but not sent. Commissions waiting for approval are
  shown apart. Agents' money already moved to their Winnings wallet is counted
  under players, never twice. Clawed-back amounts an agent still owes are shown
  as owed *to* the house.
* Partners: revenue-share wallet balances plus withdrawals requested but not paid.
"""
from __future__ import annotations

from decimal import Decimal

from django.db.models import Count, Q, Sum

ZERO = Decimal('0.00')


def _q(v) -> Decimal:
    return Decimal(v or 0).quantize(Decimal('0.01'))


def players() -> dict:
    from apps.wallet.models import BonusRollover, Wallet, WithdrawalRequest, WithdrawalSettings
    w = Wallet.objects.aggregate(
        winnings=Sum('winnings_balance'), deposit=Sum('deposit_balance'), bonus=Sum('bonus_balance'),
        with_cash=Count('pk', filter=Q(winnings_balance__gt=0) | Q(deposit_balance__gt=0)),
    )
    waiting = WithdrawalRequest.objects.filter(status=WithdrawalRequest.Status.REQUESTED).aggregate(
        amount=Sum('amount'), fee=Sum('fee'), n=Count('pk'))
    winnings, deposit = _q(w['winnings']), _q(w['deposit'])
    to_send = _q(waiting['amount']) - _q(waiting['fee'])
    deposit_fee = WithdrawalSettings.load().deposit_fee_percent
    return {
        'total': str(winnings + deposit + to_send),
        'winnings': str(winnings),
        'deposit': str(deposit),
        'deposit_after_fee': str(_q(deposit * (Decimal('100') - deposit_fee) / Decimal('100'))),
        'deposit_fee_percent': str(deposit_fee),
        'withdrawals_waiting': str(to_send),
        'withdrawals_waiting_count': waiting['n'],
        'players_with_cash': w['with_cash'],
        'bonus': str(_q(w['bonus'])),
        'aviator_bonus_profit': str(_q(BonusRollover.objects.aggregate(t=Sum('aviator_profit'))['t'])),
    }


def agents() -> dict:
    from apps.affiliates import services
    from apps.affiliates.models import Affiliate, Commission, Payout
    available = locked = in_payout = pending = owed_back = ZERO
    with_money = 0
    for a in Affiliate.objects.all():
        b = services.balance(a)
        available += b['available']
        locked += b['locked']
        in_payout += b['in_payout']
        pending += b['pending']
        # Clawed back more than the agent had: they owe it (netted off future commissions).
        net = (services._sum(a.commissions.filter(status=Commission.Status.APPROVED))
               - services._sum(a.payouts.filter(status__in=(Payout.Status.REQUESTED, Payout.Status.PAID))))
        if net < 0:
            owed_back += -net
        if b['available'] + b['locked'] + b['in_payout'] > 0:
            with_money += 1
    return {
        'total': str(_q(available + locked + in_payout)),
        'available': str(_q(available)),
        'locked': str(_q(locked)),
        'in_payout': str(_q(in_payout)),
        'pending_approval': str(_q(pending)),
        'owed_by_agents': str(_q(owed_back)),
        'agents_with_money': with_money,
    }


def partners() -> dict:
    from apps.revenue.models import ShareEntry, ShareWallet, ShareWithdrawal
    rows = []
    balance_total = ZERO
    for w in ShareWallet.objects.select_related('holder').order_by('slot'):
        bal = _q(ShareEntry.objects.filter(wallet=w).aggregate(t=Sum('amount'))['t'])
        waiting = _q(w.withdrawals.filter(status=ShareWithdrawal.Status.REQUESTED).aggregate(t=Sum('amount'))['t'])
        if bal or waiting or w.percent:
            rows.append({'slot': w.slot, 'label': w.label or f'Partner {w.slot}',
                         'holder': w.holder.get_username() if w.holder else None,
                         'balance': str(bal), 'withdrawal_waiting': str(waiting)})
        balance_total += bal
    waiting_total = _q(ShareWithdrawal.objects.filter(status=ShareWithdrawal.Status.REQUESTED).aggregate(t=Sum('amount'))['t'])
    return {
        'total': str(balance_total + waiting_total),
        'balances': str(balance_total),
        'withdrawals_waiting': str(waiting_total),
        'wallets': rows,
    }


def summary(*, include_partners: bool) -> dict:
    p, a = players(), agents()
    part = partners() if include_partners else None
    total = Decimal(p['total']) + Decimal(a['total']) + (Decimal(part['total']) if part else ZERO)
    return {'total': str(_q(total)), 'players': p, 'agents': a, 'partners': part}
