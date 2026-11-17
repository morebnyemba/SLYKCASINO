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

from django.db.models import Count, DecimalField, F, OuterRef, Q, Subquery, Sum, Value
from django.db.models.functions import Coalesce

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
    people = _owed_wallets().count()
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
        'people': people,
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
        'people': with_money,
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
        'people': sum(1 for r in rows if Decimal(r['balance']) + Decimal(r['withdrawal_waiting']) > 0),
        'balances': str(balance_total),
        'withdrawals_waiting': str(waiting_total),
        'wallets': rows,
    }


def summary(*, include_partners: bool) -> dict:
    p, a = players(), agents()
    part = partners() if include_partners else None
    total = Decimal(p['total']) + Decimal(a['total']) + (Decimal(part['total']) if part else ZERO)
    return {'total': str(_q(total)), 'players': p, 'agents': a, 'partners': part}


# -- who is owed (detail pages) ----------------------------------------------------

_MONEY = DecimalField(max_digits=14, decimal_places=2)


def _owed_wallets():
    """Every player wallet with cash owed: Winnings + Deposit + withdrawals
    requested but not sent (after fees), annotated as `waiting` and `owed`."""
    from apps.wallet.models import Wallet, WithdrawalRequest
    waiting = (WithdrawalRequest.objects.filter(player_id=OuterRef('player_id'), status=WithdrawalRequest.Status.REQUESTED)
               .values('player_id').annotate(t=Sum(F('amount') - F('fee'))).values('t'))
    return (Wallet.objects
            .annotate(waiting=Coalesce(Subquery(waiting, output_field=_MONEY), Value(ZERO, output_field=_MONEY)))
            .annotate(owed=F('winnings_balance') + F('deposit_balance') + F('waiting'))
            .filter(owed__gt=0))


def player_rows(*, q: str = '', page: int = 1, size: int = 50) -> dict:
    """Players owed money, biggest first (searchable by username)."""
    from apps.accounts.models import Player
    from apps.wallet.models import BonusRollover
    qs = _owed_wallets()
    if q:
        qs = qs.filter(player_id__in=Player.objects.filter(username__icontains=q.strip()).values('id'))
    count = qs.count()
    total = _q(qs.aggregate(t=Sum('owed'))['t'])
    rows = list(qs.order_by('-owed', 'player_id')[(page - 1) * size:page * size]
                .values('player_id', 'winnings_balance', 'deposit_balance', 'bonus_balance', 'waiting', 'owed'))
    ids = [r['player_id'] for r in rows]
    names = dict(Player.objects.filter(id__in=ids).values_list('id', 'username'))
    pots = dict(BonusRollover.objects.filter(player_id__in=ids).values_list('player_id', 'aviator_profit'))
    return {
        'count': count, 'total': str(total), 'page': page, 'page_size': size,
        'results': [{
            'player_id': r['player_id'], 'username': names.get(r['player_id'], f'#{r["player_id"]}'),
            'winnings': str(_q(r['winnings_balance'])), 'deposit': str(_q(r['deposit_balance'])),
            'withdrawals_waiting': str(_q(r['waiting'])), 'total': str(_q(r['owed'])),
            'bonus': str(_q(r['bonus_balance'])), 'aviator_bonus_profit': str(_q(pots.get(r['player_id']))),
        } for r in rows],
    }


def agent_rows() -> dict:
    """Agents owed commission (or owing some back), biggest first."""
    from apps.accounts.models import Player
    from apps.affiliates import services
    from apps.affiliates.models import Affiliate, Commission, Payout
    agents_ = list(Affiliate.objects.all())
    names = dict(Player.objects.filter(id__in=[a.player_id for a in agents_]).values_list('id', 'username'))
    rows = []
    for a in agents_:
        b = services.balance(a)
        net = (services._sum(a.commissions.filter(status=Commission.Status.APPROVED))
               - services._sum(a.payouts.filter(status__in=(Payout.Status.REQUESTED, Payout.Status.PAID))))
        owed = b['available'] + b['locked'] + b['in_payout']
        owes_back = -net if net < 0 else ZERO
        if owed <= 0 and b['pending'] <= 0 and owes_back <= 0:
            continue
        rows.append({
            'affiliate_id': a.id, 'code': a.code, 'username': names.get(a.player_id, f'#{a.player_id}'),
            'status': a.status, 'available': str(_q(b['available'])), 'locked': str(_q(b['locked'])),
            'in_payout': str(_q(b['in_payout'])), 'pending_approval': str(_q(b['pending'])),
            'owes_back': str(_q(owes_back)), 'total': str(_q(owed)),
        })
    rows.sort(key=lambda r: (-Decimal(r['total']), -Decimal(r['pending_approval']), r['code']))
    owed_rows = [r for r in rows if Decimal(r['total']) > 0]
    return {'count': len(owed_rows), 'total': str(_q(sum((Decimal(r['total']) for r in rows), ZERO))), 'results': rows}


def partner_rows() -> dict:
    data = partners()
    rows = [{**w, 'total': str(_q(Decimal(w['balance']) + Decimal(w['withdrawal_waiting'])))} for w in data['wallets']]
    rows.sort(key=lambda r: (-Decimal(r['total']), r['slot']))
    return {'count': data['people'], 'total': data['total'], 'results': rows}
