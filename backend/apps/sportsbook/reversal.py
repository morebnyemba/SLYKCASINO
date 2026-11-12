"""Reverse a ticket that was settled as won by mistake (a wrong result, a
market settled the wrong way): take the winnings back and re-mark the ticket.

What was paid is read from the ledger (every credit carries the ticket's
reference), so the reversal can never take more than the ticket actually paid.
`lost` takes back everything it paid (winnings and the returned stake); `void`
takes back the winnings and leaves the stake returned. Money comes first from
the wallet it was paid into, then from the player's other cash wallets; whatever
is no longer there (withdrawn, or bet and lost) is recorded as a shortfall — a
wallet never goes negative. A ticket is reversed once, and it is audited.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.accounts import services as accounts_services
from apps.wallet import services as wallet_services
from apps.wallet.models import Bucket, LedgerEntry

from . import helpers
from .models import Bet, BetSlip, TicketReversal

ZERO = Decimal('0.00')
CASH = (Bucket.WINNINGS, Bucket.DEPOSIT)


class ReversalError(ValueError):
    """Why the ticket can't be reversed (shown to staff)."""


def _ticket(kind: str, ticket_id: int):
    model = Bet if kind == TicketReversal.Kind.SINGLE else BetSlip
    obj = model.objects.select_for_update().filter(pk=ticket_id).first()
    if obj is None:
        raise ReversalError('No such ticket.')
    return obj


def _reference(kind: str, ticket_id: int) -> str:
    return f'bet:{ticket_id}' if kind == TicketReversal.Kind.SINGLE else f'slip:{ticket_id}'


def _paid(kind: str, ticket) -> dict[str, Decimal]:
    """What the win credited, by wallet (the multi-bet bonus included, in Bonus)."""
    if not ticket.player_id:
        return {}
    ref = _reference(kind, ticket.id)
    rows = (LedgerEntry.objects.filter(wallet__player_id=ticket.player_id, amount__gt=0,
                                       reference__in=(ref, f'{ref}:multibet-bonus'), kind__in=('bet_payout', 'bonus'))
            .values_list('bucket').annotate(t=Sum('amount')))
    return {bucket: total for bucket, total in rows if total}


def preview(kind: str, ticket_id: int, outcome: str) -> dict:
    """What reversing would take back and what the player still holds. Changes nothing."""
    with transaction.atomic():
        ticket = _ticket(kind, ticket_id)
        return _plan(kind, ticket, outcome)


def _plan(kind: str, ticket, outcome: str) -> dict:
    if outcome not in TicketReversal.Outcome.values:
        raise ReversalError('Choose lost or void.')
    if ticket.status != 'won':
        raise ReversalError(f'Only a ticket settled as won can be reversed; this one is {ticket.get_status_display().lower()}.')
    if TicketReversal.objects.filter(kind=kind, ticket_id=ticket.id).exists():
        raise ReversalError('This ticket has already been reversed.')
    paid = _paid(kind, ticket)
    owed = dict(paid)
    if outcome == TicketReversal.Outcome.VOID:
        # The stake stays returned, in the wallet it was paid back into.
        source = ticket.wallet
        owed[source] = max(owed.get(source, ZERO) - ticket.stake, ZERO)
    owed = {b: v for b, v in owed.items() if v > 0}
    balances = wallet_services.get_balances(ticket.player_id) if ticket.player_id else {}
    take: dict[str, Decimal] = {}
    left = dict(balances)
    shortfall = ZERO
    for bucket, amount in owed.items():
        # First the wallet it went into; then, for cash, the other cash wallet.
        order = [bucket] + ([b for b in CASH if b != bucket] if bucket in CASH else [])
        for b in order:
            got = min(amount, max(left.get(b, ZERO), ZERO))
            if got > 0:
                take[b] = take.get(b, ZERO) + got
                left[b] -= got
                amount -= got
        shortfall += amount
    total_owed = sum(owed.values(), ZERO)
    return {'paid': sum(paid.values(), ZERO), 'owed': total_owed, 'take': take,
            'recovered': total_owed - shortfall, 'shortfall': shortfall}


@transaction.atomic
def reverse(kind: str, ticket_id: int, *, outcome: str, reason: str, by: str, accept_shortfall: bool = False,
            freeze_withdrawals: bool = False, request=None) -> TicketReversal:
    """Take the winnings back and re-mark the ticket `lost` or `void`. Refused
    when the player no longer holds all of it, unless `accept_shortfall` (then
    what's there is taken and the rest recorded). `freeze_withdrawals` also
    stops the player withdrawing until staff lift it (Fraud & risk)."""
    reason = (reason or '').strip()
    if len(reason) < 5:
        raise ReversalError('Say why this ticket is being reversed — it goes on the record.')
    ticket = _ticket(kind, ticket_id)
    if ticket.player_id:
        from apps.wallet.models import Wallet
        Wallet.objects.select_for_update().filter(player_id=ticket.player_id).first()
    plan = _plan(kind, ticket, outcome)
    if plan['shortfall'] > 0 and not accept_shortfall:
        raise ReversalError(
            f'The player only holds ${plan["recovered"]:.2f} of the ${plan["owed"]:.2f} to take back '
            f'(${plan["shortfall"]:.2f} has been withdrawn or bet). Reverse anyway to take what is there '
            'and record the rest as owed.')
    key = (helpers.payout_idempotency_key(ticket.id) if kind == TicketReversal.Kind.SINGLE
           else helpers.slip_payout_idempotency_key(ticket.id))
    ref = _reference(kind, ticket.id)
    for bucket, amount in plan['take'].items():
        wallet_services.post_entry(
            player_id=ticket.player_id, amount=-amount, bucket=bucket,
            kind='bonus_forfeit' if bucket == Bucket.BONUS else 'bet_reversal',
            idempotency_key=f'{key}:reversal:{bucket}', reference=f'{ref}:reversal', require_non_negative=True)
    record = TicketReversal.objects.create(
        kind=kind, ticket_id=ticket.id, player_id=ticket.player_id, outcome=outcome, paid=plan['paid'],
        owed=plan['owed'], recovered=plan['recovered'], shortfall=plan['shortfall'],
        taken={b: str(v) for b, v in plan['take'].items()}, reason=reason[:300], reversed_by=by[:150])

    ticket.status = outcome
    ticket.payout = ZERO
    ticket.settled_at = timezone.now()
    fields = ['status', 'payout', 'settled_at']
    if isinstance(ticket, BetSlip):
        ticket.bonus = ZERO
        fields.append('bonus')
    ticket.save(update_fields=fields)

    if ticket.player_id:
        if ticket.wallet == Bucket.BONUS:
            from apps.wallet import bonus
            bonus.reset(ticket.player_id)       # the win no longer counts towards unlocking the Bonus wallet
        if freeze_withdrawals:
            from apps.risk import services as risk
            risk.set_restrictions(ticket.player_id, withdrawals_frozen=True)
        from apps.notifications import services as notifications
        number = f'{"S" if kind == TicketReversal.Kind.SINGLE else "M"}{ticket.id}'
        notifications.notify(
            player_id=ticket.player_id, kind='account_alert', title='Ticket corrected',
            body=(f'Ticket {number} was settled as won by mistake and has been corrected to {outcome}. '
                  f'${plan["recovered"]:.2f} was taken back from your wallet.'))
    accounts_services.audit(ticket.player_id, 'ticket_reversed', request, ticket=ref, outcome=outcome,
                            owed=str(plan['owed']), recovered=str(plan['recovered']), shortfall=str(plan['shortfall']),
                            reason=record.reason, by=by, frozen=bool(freeze_withdrawals))
    return record


def summary(record: TicketReversal) -> dict:
    return {'outcome': record.outcome, 'paid': str(record.paid), 'owed': str(record.owed),
            'recovered': str(record.recovered), 'shortfall': str(record.shortfall), 'taken': record.taken,
            'reason': record.reason, 'reversed_by': record.reversed_by, 'created_at': record.created_at.isoformat()}
