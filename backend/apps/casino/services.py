"""casino domain logic — the ONLY place casino mutations happen.

A round debits the stake from the wallet, opens a provider round, and on
settlement credits any win. All wallet movements are idempotency-keyed per round.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.wallet import services as wallet_services

from . import helpers
from .clients import CasinoProviderClient
from .models import Game, GameRound


@transaction.atomic
def start_round(*, player_id: int, game_id: int, stake: Decimal) -> GameRound:
    """Open a round: record intent (PENDING), debit the stake, confirm."""
    errors = helpers.validate_spin_request_structure({'game_id': game_id, 'stake': stake})
    if errors:
        raise ValueError('; '.join(errors))

    game = Game.objects.get(pk=game_id, is_active=True)
    rnd = GameRound.objects.create(player_id=player_id, game=game, stake=stake, status=GameRound.Status.PENDING)

    wallet_services.debit(
        player_id=player_id, amount=stake, kind='casino_debit',
        idempotency_key=helpers.round_debit_key(rnd.id), reference=f'round:{rnd.id}',
    )
    rnd.debit_confirmed = True
    rnd.provider_round_ref = CasinoProviderClient().open_round(
        player_id, game.slug, stake, helpers.round_debit_key(rnd.id),
    )
    rnd.save(update_fields=['debit_confirmed', 'provider_round_ref'])
    return rnd


@transaction.atomic
def settle_round(round_id: int, win: Decimal) -> GameRound:
    """Settle a round idempotently, crediting any win once (keyed per round)."""
    rnd = GameRound.objects.select_for_update().get(pk=round_id)
    if rnd.status == GameRound.Status.SETTLED:
        return rnd  # idempotent

    if win and win > 0:
        wallet_services.credit(
            player_id=rnd.player_id, amount=win, kind='casino_credit',
            idempotency_key=helpers.round_credit_key(rnd.id), reference=f'round:{rnd.id}',
        )
    rnd.win = win
    rnd.status = GameRound.Status.SETTLED
    rnd.settled_at = timezone.now()
    rnd.save(update_fields=['win', 'status', 'settled_at'])
    return rnd
