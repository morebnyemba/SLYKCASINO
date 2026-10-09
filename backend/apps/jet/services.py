"""Jet rounds and bets: placing, cancelling and cashing out, and the round
lifecycle the runner drives (betting -> flying -> crashed).

Money moves through the wallet ledger (casino_debit / casino_credit) with one
idempotency key per bet and purpose, so nothing is ever paid or taken twice.
Cash-outs are decided by the server clock against the round's start time —
the player's browser only asks.
"""
from __future__ import annotations

import json
import logging
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.db import transaction
from django.db.models import F
from django.utils import timezone

from apps.wallet import services as wallet_services

from . import engine
from .models import JetBet, JetRound, JetSettings

logger = logging.getLogger(__name__)

CHANNEL = 'jet'
# Pause between a crash and the next round's betting window.
COOLDOWN_SECONDS = 3
HISTORY_SIZE = 40


class JetError(ValueError):
    """A bet or cash-out that can't go through; the message is for the player."""


# -- realtime -----------------------------------------------------------------

def publish(payload: dict) -> None:
    """Fan a frame out to everyone watching (best effort, after commit)."""
    from apps.livechat.clients import RealtimePublisherClient
    body = json.dumps(payload, default=str)

    def send():
        try:
            RealtimePublisherClient().publish(CHANNEL, body)
        except Exception:  # noqa: BLE001 — realtime must never break the game
            logger.warning('jet publish failed', exc_info=True)
    transaction.on_commit(send)


def publish_now(payload: dict) -> None:
    """Publish outside any transaction (runner status frames)."""
    from apps.livechat.clients import RealtimePublisherClient
    try:
        RealtimePublisherClient().publish(CHANNEL, json.dumps(payload, default=str))
    except Exception:  # noqa: BLE001
        logger.warning('jet publish failed', exc_info=True)


def iso(dt) -> Optional[str]:
    return dt.isoformat() if dt else None


def round_payload(rnd: JetRound) -> dict:
    """The round as players may see it: the crash point and seed only once crashed."""
    crashed = rnd.status == JetRound.Status.CRASHED
    return {
        'id': rnd.id, 'status': rnd.status, 'seed_hash': rnd.seed_hash,
        'betting_ends_at': iso(rnd.betting_ends_at), 'started_at': iso(rnd.started_at),
        'crashed_at': iso(rnd.crashed_at),
        'crash_point': str(rnd.crash_point) if crashed else None,
        'server_seed': rnd.server_seed if crashed else None,
        'bet_count': rnd.bet_count, 'total_stake': str(rnd.total_stake),
    }


def bet_payload(bet: JetBet, *, mine: bool = False) -> dict:
    data = {
        'id': bet.id, 'round': bet.round_id, 'player': bet.display_name, 'slot': bet.slot,
        'stake': str(bet.stake), 'status': bet.status,
        'cashout_multiplier': str(bet.cashout_multiplier) if bet.cashout_multiplier else None,
        'payout': str(bet.payout),
    }
    if mine:
        data['auto_cashout'] = str(bet.auto_cashout) if bet.auto_cashout else None
    return data


def settings_payload(cfg: JetSettings) -> dict:
    return {
        'enabled': cfg.enabled, 'display_name': cfg.display_name,
        'house_edge_percent': str(cfg.house_edge_percent),
        'rtp_percent': str(Decimal('100') - cfg.house_edge_percent),
        'min_bet': str(cfg.min_bet), 'max_bet': str(cfg.max_bet), 'max_win': str(cfg.max_win),
        'max_multiplier': str(cfg.max_multiplier), 'round_stake_limit': str(cfg.round_stake_limit),
        'betting_seconds': cfg.betting_seconds, 'rate': engine.RATE,
    }


def current_round() -> Optional[JetRound]:
    return JetRound.objects.exclude(status=JetRound.Status.CRASHED).order_by('-id').first()


def history(limit: int = HISTORY_SIZE) -> list[dict]:
    rows = JetRound.objects.filter(status=JetRound.Status.CRASHED).order_by('-id')[:limit]
    return [{'id': r.id, 'crash_point': str(r.crash_point)} for r in rows]


# -- player actions -----------------------------------------------------------

def _money(value, field: str) -> Decimal:
    try:
        amount = Decimal(str(value)).quantize(engine.CENT)
    except (InvalidOperation, ValueError, TypeError):
        raise JetError(f'Enter a valid {field}.')
    return amount


@transaction.atomic
def place_bet(*, player, stake, slot: int = 1, auto_cashout=None, now=None) -> JetBet:
    """Bet on the round that is taking bets. Raises JetError (shown to the
    player) or wallet_services.InsufficientFunds."""
    from apps.accounts import services as accounts_services

    now = now or timezone.now()
    cfg = JetSettings.load()
    if not cfg.enabled:
        raise JetError('Jet is paused right now.')
    try:
        accounts_services.check_responsible_gambling(player)
    except ValueError as exc:
        raise JetError(str(exc))
    if slot not in (1, 2):
        raise JetError('Choose bet 1 or bet 2.')
    stake = _money(stake, 'stake')
    if stake < cfg.min_bet or stake > cfg.max_bet:
        raise JetError(f'Bets are ${cfg.min_bet:.2f} to ${cfg.max_bet:.2f}.')
    auto = None
    if auto_cashout not in (None, ''):
        auto = _money(auto_cashout, 'auto cash-out')
        if auto < Decimal('1.01') or auto > cfg.max_multiplier:
            raise JetError(f'Auto cash-out must be between 1.01x and {cfg.max_multiplier}x.')

    rnd = (JetRound.objects.select_for_update()
           .filter(status=JetRound.Status.BETTING).order_by('-id').first())
    if rnd is None or now >= rnd.betting_ends_at:
        raise JetError('Bets for this round are closed — wait for the next one.')
    if JetBet.objects.filter(round=rnd, player_id=player.id, slot=slot).exists():
        raise JetError('You already have a bet in this slot.')
    if rnd.total_stake + stake > cfg.round_stake_limit:
        raise JetError('This round is full — try the next one.')

    bet = JetBet.objects.create(
        round=rnd, player_id=player.id, display_name=engine.mask_name(player.username),
        slot=slot, stake=stake, auto_cashout=auto,
    )
    wallet_services.debit(
        player_id=player.id, amount=stake, kind='casino_debit',
        idempotency_key=f'jet:stake:{bet.id}', reference=f'jet:round:{rnd.id}:bet:{bet.id}',
    )
    JetRound.objects.filter(pk=rnd.pk).update(total_stake=F('total_stake') + stake, bet_count=F('bet_count') + 1)
    publish({'type': 'bet', 'bet': bet_payload(bet)})
    return bet


@transaction.atomic
def cancel_bet(*, player_id: int, bet_id: int, now=None) -> JetBet:
    """Take a bet back while the countdown is still running."""
    now = now or timezone.now()
    bet = JetBet.objects.select_for_update().select_related('round').filter(pk=bet_id, player_id=player_id).first()
    if bet is None:
        raise JetError('Bet not found.')
    rnd = bet.round
    if bet.status != JetBet.Status.ACTIVE or rnd.status != JetRound.Status.BETTING or now >= rnd.betting_ends_at:
        raise JetError('This bet can no longer be cancelled.')
    _refund(bet, now)
    JetRound.objects.filter(pk=rnd.pk).update(total_stake=F('total_stake') - bet.stake, bet_count=F('bet_count') - 1)
    publish({'type': 'cancel', 'bet': bet.id, 'round': rnd.id})
    return bet


def _refund(bet: JetBet, now) -> None:
    wallet_services.credit(
        player_id=bet.player_id, amount=bet.stake, kind='casino_credit',
        idempotency_key=f'jet:refund:{bet.id}', reference=f'jet:round:{bet.round_id}:bet:{bet.id}:refund',
    )
    bet.status = JetBet.Status.REFUNDED
    bet.settled_at = now
    bet.save(update_fields=['status', 'settled_at'])


def _pay(bet: JetBet, multiplier: Decimal, cfg: JetSettings, now) -> JetBet:
    """Cash a riding bet out at `multiplier` (caller holds the row lock)."""
    payout = engine.payout_for(bet.stake, multiplier, cfg.max_win)
    wallet_services.credit(
        player_id=bet.player_id, amount=payout, kind='casino_credit',
        idempotency_key=f'jet:payout:{bet.id}', reference=f'jet:round:{bet.round_id}:bet:{bet.id}:cashout',
    )
    bet.status = JetBet.Status.CASHED
    bet.cashout_multiplier = multiplier
    bet.payout = payout
    bet.settled_at = now
    bet.save(update_fields=['status', 'cashout_multiplier', 'payout', 'settled_at'])
    JetRound.objects.filter(pk=bet.round_id).update(total_payout=F('total_payout') + payout)
    publish({'type': 'cashout', 'bet': bet_payload(bet)})
    return bet


def _target(bet: JetBet, cfg: JetSettings) -> Decimal:
    """Where a bet cashes out by itself: its auto cash-out, or the max win."""
    cap = engine.max_win_multiplier(bet.stake, cfg.max_win)
    return min(bet.auto_cashout, cap) if bet.auto_cashout else cap


@transaction.atomic
def cash_out(*, player_id: int, bet_id: int, now=None) -> JetBet:
    """Cash out at the multiplier the plane is at now, by the server clock."""
    now = now or timezone.now()
    cfg = JetSettings.load()
    bet = JetBet.objects.select_for_update().select_related('round').filter(pk=bet_id, player_id=player_id).first()
    if bet is None:
        raise JetError('Bet not found.')
    rnd = bet.round
    if bet.status == JetBet.Status.CASHED:
        raise JetError(f'Already cashed out at {bet.cashout_multiplier}x.')
    if bet.status != JetBet.Status.ACTIVE:
        raise JetError('This bet is settled.')
    if rnd.status == JetRound.Status.BETTING:
        raise JetError('The round hasn’t started yet — cancel the bet instead.')
    if rnd.started_at is None:
        raise JetError('The round hasn’t started yet.')
    multiplier = engine.multiplier_at((now - rnd.started_at).total_seconds())
    if rnd.status == JetRound.Status.CRASHED or multiplier >= rnd.crash_point:
        raise JetError(f'Too late — the plane flew away at {rnd.crash_point}x.')
    return _pay(bet, min(multiplier, _target(bet, cfg)), cfg, now)


# -- round lifecycle (driven by the runner) -----------------------------------

@transaction.atomic
def open_round(*, now=None) -> JetRound:
    now = now or timezone.now()
    cfg = JetSettings.load()
    seed = engine.new_seed()
    rnd = JetRound.objects.create(
        server_seed=seed, seed_hash=engine.seed_hash(seed), crash_point=engine.ONE,
        house_edge_percent=cfg.house_edge_percent,
        betting_ends_at=now + timedelta(seconds=cfg.betting_seconds),
    )
    # The crash point is derived from the round id, so it's fixed once the row exists.
    rnd.crash_point = engine.crash_point(seed, rnd.id, cfg.house_edge_percent, cfg.max_multiplier)
    rnd.save(update_fields=['crash_point'])
    publish({'type': 'round', 'round': round_payload(rnd), 'server_time': iso(now)})
    return rnd


@transaction.atomic
def start_flight(round_id: int, *, now=None) -> JetRound:
    now = now or timezone.now()
    rnd = JetRound.objects.select_for_update().get(pk=round_id)
    if rnd.status == JetRound.Status.BETTING:
        rnd.status = JetRound.Status.FLYING
        rnd.started_at = now
        rnd.save(update_fields=['status', 'started_at'])
        publish({'type': 'round', 'round': round_payload(rnd), 'server_time': iso(now)})
    return rnd


def settle_auto_cashouts(round_id: int, *, now=None) -> int:
    """Pay riding bets whose auto cash-out (or max win) the plane has passed.
    Returns how many were paid."""
    now = now or timezone.now()
    cfg = JetSettings.load()
    rnd = JetRound.objects.get(pk=round_id)
    if rnd.status != JetRound.Status.FLYING or rnd.started_at is None:
        return 0
    reached = min(engine.multiplier_at((now - rnd.started_at).total_seconds()), rnd.crash_point)
    paid = 0
    for bet_id in list(JetBet.objects.filter(round=rnd, status=JetBet.Status.ACTIVE).values_list('id', flat=True)):
        with transaction.atomic():
            bet = JetBet.objects.select_for_update().get(pk=bet_id)
            if bet.status != JetBet.Status.ACTIVE:
                continue
            target = _target(bet, cfg)
            if target <= reached:
                _pay(bet, target, cfg, now)
                paid += 1
    return paid


@transaction.atomic
def crash_round(round_id: int, *, now=None) -> JetRound:
    """End the flight at its crash point: auto cash-outs at or below it pay,
    every other riding bet loses, and the seed is revealed."""
    now = now or timezone.now()
    cfg = JetSettings.load()
    rnd = JetRound.objects.select_for_update().get(pk=round_id)
    if rnd.status == JetRound.Status.CRASHED:
        return rnd
    for bet in JetBet.objects.select_for_update().filter(round=rnd, status=JetBet.Status.ACTIVE):
        target = _target(bet, cfg)
        if target <= rnd.crash_point:
            _pay(bet, target, cfg, now)
        else:
            bet.status = JetBet.Status.LOST
            bet.settled_at = now
            bet.save(update_fields=['status', 'settled_at'])
    rnd.status = JetRound.Status.CRASHED
    rnd.crashed_at = now
    if rnd.started_at is None:
        rnd.started_at = now
    rnd.save(update_fields=['status', 'crashed_at', 'started_at'])
    rnd.refresh_from_db()
    publish({'type': 'crash', 'round': round_payload(rnd), 'server_time': iso(now)})
    return rnd


@transaction.atomic
def recover(*, now=None) -> int:
    """After a restart: a round still taking bets refunds them; a round that was
    flying settles its auto cash-outs and refunds bets nobody could cash out
    while the game was down. Returns rounds closed."""
    now = now or timezone.now()
    cfg = JetSettings.load()
    closed = 0
    for rnd in JetRound.objects.select_for_update().exclude(status=JetRound.Status.CRASHED):
        for bet in JetBet.objects.select_for_update().filter(round=rnd, status=JetBet.Status.ACTIVE):
            if rnd.status == JetRound.Status.FLYING and _target(bet, cfg) <= rnd.crash_point:
                _pay(bet, _target(bet, cfg), cfg, now)
            else:
                _refund(bet, now)
        rnd.status = JetRound.Status.CRASHED
        rnd.crashed_at = now
        rnd.started_at = rnd.started_at or now
        rnd.save(update_fields=['status', 'crashed_at', 'started_at'])
        closed += 1
    return closed


def flight_seconds(rnd: JetRound) -> float:
    return engine.seconds_to(rnd.crash_point)


def erase_player_data(player_id: int) -> int:
    """Permanently delete a player's Aviator bets (round totals are kept)."""
    return JetBet.objects.filter(player_id=player_id).delete()[0]
