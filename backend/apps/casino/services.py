"""casino domain logic — the ONLY place casino mutations happen.

A round debits the stake from the wallet, opens a provider round, and on
settlement credits any win. All wallet movements are idempotency-keyed per round.
"""
from __future__ import annotations

from decimal import Decimal

from django.db import transaction
from django.utils import timezone

from apps.wallet import services as wallet_services

from . import crash_engine, helpers
from .clients import CasinoProviderClient
from .models import CrashRound, Game, GameRound


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
    _record_tournament_play(rnd.player_id, rnd.stake)
    return rnd


# -- crash (Aviator-style) ---------------------------------------------------

@transaction.atomic
def place_crash_bet(*, player_id: int, stake: Decimal) -> CrashRound:
    """Open a crash round: commit a provably-fair crash point and debit the stake.

    The crash point is derived from `server_seed` (committed via its hash) and the
    round id as the nonce, so it is fixed before the player can act and verifiable
    after settlement."""
    if stake is None or stake <= 0:
        raise ValueError('stake must be positive')

    seed = crash_engine.new_server_seed()
    rnd = CrashRound.objects.create(
        player_id=player_id, stake=stake,
        crash_point=Decimal('1.00'),  # placeholder until nonce (the id) is known
        server_seed=seed, server_seed_hash=crash_engine.seed_hash(seed),
        status=CrashRound.Status.RUNNING,
    )
    rnd.nonce = rnd.id
    rnd.crash_point = crash_engine.crash_point(seed, rnd.nonce)

    wallet_services.debit(
        player_id=player_id, amount=stake, kind='casino_debit',
        idempotency_key=helpers.crash_debit_key(rnd.id), reference=f'crash:{rnd.id}',
    )
    rnd.debit_confirmed = True
    rnd.save(update_fields=['nonce', 'crash_point', 'debit_confirmed'])
    return rnd


@transaction.atomic
def cashout_crash(*, player_id: int, crash_id: int, target=None) -> CrashRound:
    """Settle a crash round. The server computes the live multiplier from elapsed
    time and is authoritative: a cash-out at or beyond the (hidden) crash point
    busts; otherwise the player wins stake × the chosen multiplier.

    `target` is the player's intended cash-out multiplier (e.g. an auto cash-out).
    It is honoured only when strictly below the crash point, which keeps the house
    edge intact while letting auto cash-outs land exactly on target despite
    network latency."""
    rnd = CrashRound.objects.select_for_update().get(pk=crash_id, player_id=player_id)
    if rnd.status != CrashRound.Status.RUNNING:
        return rnd  # idempotent — already settled

    elapsed = (timezone.now() - rnd.created_at).total_seconds()
    current = crash_engine.multiplier_at(elapsed)
    chosen = target if (target is not None and target < current) else current

    if chosen >= rnd.crash_point:
        rnd.status = CrashRound.Status.BUSTED
        rnd.win = Decimal('0')
    else:
        win = (rnd.stake * chosen).quantize(Decimal('0.01'))
        wallet_services.credit(
            player_id=player_id, amount=win, kind='casino_credit',
            idempotency_key=helpers.crash_credit_key(rnd.id), reference=f'crash:{rnd.id}',
        )
        rnd.status = CrashRound.Status.CASHED
        rnd.cashout_multiplier = chosen
        rnd.win = win

    rnd.settled_at = timezone.now()
    rnd.save(update_fields=['status', 'cashout_multiplier', 'win', 'settled_at'])
    _record_tournament_play(player_id, rnd.stake)
    return rnd


def _record_tournament_play(player_id: int, wagered: Decimal) -> None:
    """Best-effort: credit wagering toward any live tournaments. Never blocks a
    settlement if the promotions app is unavailable."""
    try:
        from apps.promotions import services as promo_services
        promo_services.record_tournament_play(player_id=player_id, wagered=wagered)
    except Exception:  # noqa: BLE001 — scoring is non-critical to the game outcome
        pass
