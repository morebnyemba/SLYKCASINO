"""sportsbook domain logic — the ONLY place sportsbook mutations happen.

Bet placement debits the wallet via wallet.services (cross-context, by ID), and
settlement credits payouts. Both use deterministic idempotency keys so retries
and recovery never double-charge or double-pay.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.db import transaction
from django.utils import timezone

from apps.wallet import services as wallet_services

from . import helpers, utils
from .dtos import BetDTO
from .models import Bet, Event


# -- reads -------------------------------------------------------------------

def list_events(*, featured: Optional[bool] = None, sport: Optional[str] = None):
    qs = Event.objects.all()
    if featured:
        qs = qs.filter(featured=True)
    if sport:
        qs = qs.filter(sport=sport)
    return qs


def to_dto(bet: Bet) -> BetDTO:
    return BetDTO.model_validate(bet)


# -- mutations ---------------------------------------------------------------

@transaction.atomic
def place_bet(*, event: str, stake: Decimal, odds: Decimal, player_id: Optional[int] = None) -> Bet:
    """Place a bet. For an identified player the stake is debited from the wallet
    atomically; raising InsufficientFunds rolls the whole placement back."""
    errors = helpers.validate_bet_request_structure({'event': event, 'stake': stake, 'odds': odds})
    if errors:
        raise ValueError('; '.join(errors))

    if player_id is None:
        # Anonymous compatibility path — no wallet movement (documented).
        return Bet.objects.create(
            event=event, stake=utils.quantize(stake), odds=odds, status=Bet.Status.OPEN,
        )

    # Record intent as PENDING, debit the stake, then mark OPEN.
    bet = Bet.objects.create(
        player_id=player_id, event=event, stake=utils.quantize(stake),
        odds=odds, status=Bet.Status.PENDING,
    )
    wallet_services.debit(
        player_id=player_id, amount=bet.stake, kind='bet_stake',
        idempotency_key=helpers.stake_idempotency_key(bet.id), reference=f'bet:{bet.id}',
    )
    bet.status = Bet.Status.OPEN
    bet.save(update_fields=['status'])
    return bet


@transaction.atomic
def settle_bet(bet_id: int, outcome: str) -> Bet:
    """Settle a bet idempotently. Re-settling an already-settled bet is a no-op
    (status guard) and payout credits are idempotency-keyed per bet."""
    bet = Bet.objects.select_for_update().get(pk=bet_id)
    if bet.status not in (Bet.Status.OPEN, Bet.Status.PENDING):
        return bet  # already settled — idempotent

    if outcome == 'won':
        payout = utils.calculate_payout(bet.stake, bet.odds)
        if bet.player_id:
            wallet_services.credit(
                player_id=bet.player_id, amount=payout, kind='bet_payout',
                idempotency_key=helpers.payout_idempotency_key(bet.id), reference=f'bet:{bet.id}',
            )
        bet.payout = payout
        bet.status = Bet.Status.WON
    elif outcome == 'void':
        if bet.player_id:
            wallet_services.credit(
                player_id=bet.player_id, amount=bet.stake, kind='bet_payout',
                idempotency_key=f'{helpers.payout_idempotency_key(bet.id)}:refund',
                reference=f'bet:{bet.id}',
            )
        bet.status = Bet.Status.VOID
    else:
        bet.status = Bet.Status.LOST

    bet.settled_at = timezone.now()
    bet.save(update_fields=['status', 'payout', 'settled_at'])

    # Notify the player about the settlement result (lazy import avoids circular).
    if bet.player_id:
        from apps.notifications import services as notif_services
        if outcome == 'won':
            notif_services.notify(
                player_id=bet.player_id,
                kind='bet_won',
                title='Bet won!',
                body=f'Your bet #{bet.id} won. Payout: {bet.payout}',
            )
        elif outcome == 'void':
            notif_services.notify(
                player_id=bet.player_id,
                kind='account_alert',
                title='Bet voided',
                body=f'Your bet #{bet.id} has been voided and your stake refunded.',
            )
        else:
            notif_services.notify(
                player_id=bet.player_id,
                kind='bet_lost',
                title='Bet lost',
                body=f'Your bet #{bet.id} did not win this time.',
            )

    return bet
