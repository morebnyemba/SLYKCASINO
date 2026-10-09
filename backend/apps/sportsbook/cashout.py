"""Cash-out: settle an open ticket early at what it is worth right now.

The offer is the ticket's fair value at current prices less the operator's
margin:

    value = stake x (odds taken) / (current odds of every unresolved pick) x (1 - margin)

Picks that already won keep their odds in the numerator (they are banked),
void picks drop out, and a lost pick ends the offer. A pick whose market is
suspended, or a match past kick-off that isn't trading in play, means no offer
right now — never a price from stale odds.

A full cash-out pays the offer and ends the ticket (CASHED_OUT). A partial one
pays part of it and retires the matching share of the stake; the rest keeps
riding at the original odds and settles as normal.
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_DOWN, Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.wallet import services as wallet_services

from . import utils
from .models import Bet, BetLeg, BetSlip, Cashout, CashoutSettings, Event, MarketOutcome, Selection

CENT = Decimal('0.01')


class CashoutUnavailable(ValueError):
    """No cash-out offer on this ticket right now (the message says why)."""


class CashoutChanged(ValueError):
    """The offer moved below what the player accepted; `value` is the new one."""

    def __init__(self, value: Decimal):
        super().__init__(f'The cash-out value changed to ${value:.2f}.')
        self.value = value


@dataclass(frozen=True)
class Offer:
    available: bool
    value: Decimal = Decimal('0')
    reason: str = ''
    partial: bool = False
    min_amount: Decimal = Decimal('0')

    def as_dict(self) -> dict:
        return {
            'available': self.available, 'value': str(self.value) if self.available else None,
            'reason': self.reason, 'partial': self.partial and self.available,
            'min_amount': f'{self.min_amount:.2f}',
        }


def _main_price(event: Event, selection: str) -> Optional[Decimal]:
    return {
        Selection.HOME: event.odds, Selection.DRAW: event.odds_draw, Selection.AWAY: event.odds_away,
    }.get(selection)


def _current_price(event: Optional[Event], selection: str, outcome: Optional[MarketOutcome],
                   cfg: CashoutSettings, *, now=None) -> Optional[Decimal]:
    """What the pick trades at right now, or None if it can't be priced
    (suspended, closed, or past kick-off without in-play trading)."""
    from .services import _started, in_play_bettable, pre_match_bettable

    if outcome is not None:
        market = outcome.market
        event = market.event
        if market.settled or not market.is_open or not outcome.is_open or outcome.result != MarketOutcome.Result.PENDING:
            return None
        if _started(event):
            if not cfg.in_play or not in_play_bettable(event, now=now):
                return None
        elif not event.is_open:
            return None
        price = outcome.odds
    else:
        if event is None:
            return None  # free-text bet with no market behind it
        if _started(event):
            if not cfg.in_play or not in_play_bettable(event, now=now) or not event.live_main_open:
                return None
        elif not pre_match_bettable(event):
            return None
        price = _main_price(event, selection)
    if price is None or Decimal(price) <= 1:
        return None
    return Decimal(price)


def _priced(stake: Decimal, numerator: Decimal, denominator: Decimal, cfg: CashoutSettings) -> Decimal:
    keep = (Decimal('100') - Decimal(cfg.margin_percent)) / Decimal('100')
    value = Decimal(stake) * numerator / denominator * keep
    return value.quantize(CENT, rounding=ROUND_DOWN)


def _finish(value: Decimal, cfg: CashoutSettings) -> Offer:
    min_amount = Decimal(cfg.min_amount)
    if value < min_amount:
        return Offer(False, reason=f'Cash-out is offered from ${min_amount:.2f}.', min_amount=min_amount)
    return Offer(True, value=value, partial=cfg.allow_partial and value >= 2 * min_amount, min_amount=min_amount)


def bet_offer(bet: Bet, cfg: Optional[CashoutSettings] = None, *, now=None) -> Offer:
    cfg = cfg or CashoutSettings.load()
    if not cfg.enabled:
        return Offer(False, reason='Cash-out is not available.')
    if bet.status != Bet.Status.OPEN or not bet.player_id:
        return Offer(False, reason='This bet can’t be cashed out.')
    outcome = bet.outcome_ref
    price = _current_price(bet.event_ref, bet.selection, outcome, cfg, now=now)
    if price is None:
        return Offer(False, reason='Cash-out is suspended — the market isn’t trading right now.')
    return _finish(_priced(bet.stake, Decimal(bet.odds), price, cfg), cfg)


def slip_offer(slip: BetSlip, cfg: Optional[CashoutSettings] = None, *, now=None) -> Offer:
    cfg = cfg or CashoutSettings.load()
    if not cfg.enabled:
        return Offer(False, reason='Cash-out is not available.')
    if slip.status != BetSlip.Status.OPEN or not slip.player_id:
        return Offer(False, reason='This ticket can’t be cashed out.')
    numerator, denominator, pending = Decimal('1'), Decimal('1'), 0
    for leg in slip.legs.all():
        if leg.result == BetLeg.Result.LOST:
            return Offer(False, reason='A selection on this ticket has lost.')
        if leg.result == BetLeg.Result.VOID:
            continue
        numerator *= Decimal(leg.odds)
        if leg.result == BetLeg.Result.WON:
            continue
        price = _current_price(leg.event_ref, leg.selection, leg.outcome_ref, cfg, now=now)
        if price is None:
            return Offer(False, reason='Cash-out is suspended — a selection isn’t trading right now.')
        denominator *= price
        pending += 1
    if pending == 0:
        return Offer(False, reason='Every selection is decided — the ticket is being settled.')
    return _finish(_priced(slip.stake, numerator, denominator, cfg), cfg)


def _locked_ticket(kind: str, ticket_id: int, player_id: int):
    model = Bet if kind == 'bet' else BetSlip
    qs = model.objects.select_for_update()
    if kind == 'bet':
        qs = qs.select_related('event_ref', 'outcome_ref__market__event')
    ticket = qs.filter(pk=ticket_id, player_id=player_id).first()
    if ticket is None:
        raise CashoutUnavailable('Ticket not found.')
    return ticket


@transaction.atomic
def cash_out(*, kind: str, ticket_id: int, player_id: int, expected: Decimal,
             amount: Optional[Decimal] = None) -> tuple[object, Cashout]:
    """Take the cash-out on a player's ticket. `expected` is the offer the
    player saw: if the value has since dropped below it, CashoutChanged is
    raised with the new value instead of paying. `amount` (partial cash-out)
    takes only that much and leaves the rest of the stake riding."""
    if kind not in ('bet', 'slip'):
        raise CashoutUnavailable('Unknown ticket type.')
    cfg = CashoutSettings.load()
    ticket = _locked_ticket(kind, ticket_id, player_id)
    offer = bet_offer(ticket, cfg) if kind == 'bet' else slip_offer(ticket, cfg)
    if not offer.available:
        raise CashoutUnavailable(offer.reason)
    expected = utils.quantize(expected)
    if offer.value < expected:
        raise CashoutChanged(offer.value)

    value = offer.value
    full = amount is None or utils.quantize(amount) >= value
    if full:
        paid, stake_portion = value, ticket.stake
    else:
        paid = utils.quantize(amount)
        if not offer.partial:
            raise CashoutUnavailable('Partial cash-out isn’t available on this ticket — cash out in full instead.')
        if paid < offer.min_amount or value - paid < offer.min_amount:
            raise CashoutUnavailable(
                f'Cash out at least ${offer.min_amount:.2f} and leave at least ${offer.min_amount:.2f} riding.',
            )
        stake_portion = utils.quantize(Decimal(ticket.stake) * paid / value)
        if stake_portion <= 0 or stake_portion >= ticket.stake:
            raise CashoutUnavailable('That amount can’t be cashed out — try a different amount.')

    record = Cashout.objects.create(
        bet=ticket if kind == 'bet' else None, slip=ticket if kind == 'slip' else None,
        player_id=player_id, amount=paid, stake_portion=stake_portion, full=full,
    )
    wallet_services.credit(
        player_id=player_id, amount=paid, kind='bet_payout',
        idempotency_key=f'cashout:{record.id}', reference=f'{kind}:{ticket.id}:cashout',
    )
    now = timezone.now()
    ticket.cashout_paid = Decimal(ticket.cashout_paid) + paid
    ticket.stake_cashed_out = Decimal(ticket.stake_cashed_out) + stake_portion
    ticket.cashed_out_at = now
    fields = ['cashout_paid', 'stake_cashed_out', 'cashed_out_at']
    if full:
        ticket.status = ticket.Status.CASHED_OUT
        ticket.payout = ticket.cashout_paid
        ticket.settled_at = now
        fields += ['status', 'payout', 'settled_at']
    else:
        ticket.stake = Decimal(ticket.stake) - stake_portion
        fields.append('stake')
    ticket.save(update_fields=fields)

    from apps.notifications import services as notif_services
    label = f'#{ticket.id}' if kind == 'bet' else f'M{ticket.id}'
    notif_services.notify(
        player_id=player_id, kind='bet_won',
        title='Cashed out' if full else 'Partly cashed out',
        body=f'${paid:.2f} from ticket {label} is in your wallet.'
             + ('' if full else f' ${ticket.stake:.2f} of your stake is still riding.'),
    )
    return ticket, record
