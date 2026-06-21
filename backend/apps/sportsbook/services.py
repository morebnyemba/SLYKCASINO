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
from .clients import ApiFootballClient, FixtureUpdate, OddsSnapshot, TeamInfo
from .dtos import BetDTO
from .models import Bet, BetLeg, BetSlip, Event, Selection, Team


# -- reads -------------------------------------------------------------------

def list_events(*, featured: Optional[bool] = None, sport: Optional[str] = None):
    qs = Event.objects.all()
    if featured:
        qs = qs.filter(featured=True)
    if sport:
        qs = qs.filter(sport=sport)
    return qs


def _outcome_for(selection: str, result: str) -> str:
    """Map a wager's backed selection against the event result to a settle outcome."""
    if result == 'void':
        return 'void'
    return 'won' if selection == result else 'lost'


def to_dto(bet: Bet) -> BetDTO:
    return BetDTO.model_validate(bet)


# -- mutations ---------------------------------------------------------------

@transaction.atomic
def place_bet(
    *, event: str, stake: Decimal, odds: Decimal, player_id: Optional[int] = None,
    event_id: Optional[int] = None, selection: str = Selection.HOME,
) -> Bet:
    """Place a bet. For an identified player the stake is debited from the wallet
    atomically; raising InsufficientFunds rolls the whole placement back.

    `event_id`/`selection` soft-link the bet to its market so a single result can
    settle every bet on it (see settle_event)."""
    errors = helpers.validate_bet_request_structure({'event': event, 'stake': stake, 'odds': odds})
    if errors:
        raise ValueError('; '.join(errors))
    if selection not in Selection.values:
        selection = Selection.HOME

    if player_id is None:
        # Anonymous compatibility path — no wallet movement (documented).
        return Bet.objects.create(
            event=event, stake=utils.quantize(stake), odds=odds, status=Bet.Status.OPEN,
            event_ref_id=event_id, selection=selection,
        )

    # Record intent as PENDING, debit the stake, then mark OPEN.
    bet = Bet.objects.create(
        player_id=player_id, event=event, stake=utils.quantize(stake),
        odds=odds, status=Bet.Status.PENDING, event_ref_id=event_id, selection=selection,
    )
    wallet_services.debit(
        player_id=player_id, amount=bet.stake, kind='bet_stake',
        idempotency_key=helpers.stake_idempotency_key(bet.id), reference=f'bet:{bet.id}',
    )
    bet.status = Bet.Status.OPEN
    bet.save(update_fields=['status'])
    return bet


@transaction.atomic
def settle_event(event_id: int, result: str) -> int:
    """Settle every open bet linked to an event from a single result.

    `result` is one of 'home' | 'draw' | 'away' | 'void'. Each bet is won/lost by
    comparing its backed selection; settlement is delegated to settle_bet so wallet
    payouts stay idempotent. Returns the number of bets settled."""
    if result not in (*Selection.values, 'void'):
        raise ValueError("result must be 'home', 'draw', 'away', or 'void'")

    bets = Bet.objects.filter(
        event_ref_id=event_id, status__in=(Bet.Status.OPEN, Bet.Status.PENDING),
    ).values_list('id', 'selection')
    settled = 0
    for bet_id, selection in list(bets):
        settle_bet(bet_id, _outcome_for(selection, result))
        settled += 1

    # Resolve any accumulator legs on this event, then re-check their parent slips.
    legs = BetLeg.objects.filter(
        event_ref_id=event_id, result=BetLeg.Result.PENDING,
        slip__status__in=(BetSlip.Status.OPEN, BetSlip.Status.PENDING),
    ).select_related('slip')
    slips = {}
    for leg in legs:
        outcome = _outcome_for(leg.selection, result)
        leg.result = {'won': BetLeg.Result.WON, 'lost': BetLeg.Result.LOST}.get(outcome, BetLeg.Result.VOID)
        leg.save(update_fields=['result'])
        slips[leg.slip_id] = leg.slip
    for slip in slips.values():
        _settle_slip_if_ready(slip.id)

    return settled


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


# -- accumulators ------------------------------------------------------------

@transaction.atomic
def place_accumulator(*, stake: Decimal, legs: list[dict], player_id: Optional[int] = None) -> BetSlip:
    """Place a multi-leg accumulator. `legs` is a list of dicts with keys
    `event` (label), `odds`, optional `event_id` and `selection`. Combined odds
    are the product of every leg; a single stake is debited for an identified
    player, rolling back atomically on InsufficientFunds."""
    if not legs or len(legs) < 2:
        raise ValueError('an accumulator needs at least 2 selections')

    combined = Decimal('1')
    normalised: list[dict] = []
    for leg in legs:
        errors = helpers.validate_bet_request_structure({
            'event': leg.get('event'), 'stake': stake, 'odds': leg.get('odds'),
        })
        if errors:
            raise ValueError('; '.join(errors))
        odds = Decimal(str(leg['odds']))
        selection = leg.get('selection') or Selection.HOME
        if selection not in Selection.values:
            selection = Selection.HOME
        combined *= odds
        normalised.append({
            'event': leg['event'], 'odds': odds, 'selection': selection,
            'event_id': leg.get('event_id'),
        })
    combined_odds = utils.quantize(combined)

    status_ = BetSlip.Status.OPEN if player_id is None else BetSlip.Status.PENDING
    slip = BetSlip.objects.create(
        player_id=player_id, stake=utils.quantize(stake),
        combined_odds=combined_odds, status=status_,
    )
    BetLeg.objects.bulk_create([
        BetLeg(slip=slip, event=n['event'], odds=n['odds'], selection=n['selection'],
               event_ref_id=n['event_id'])
        for n in normalised
    ])

    if player_id is not None:
        wallet_services.debit(
            player_id=player_id, amount=slip.stake, kind='bet_stake',
            idempotency_key=helpers.slip_stake_idempotency_key(slip.id), reference=f'slip:{slip.id}',
        )
        slip.status = BetSlip.Status.OPEN
        slip.save(update_fields=['status'])
    return slip


@transaction.atomic
def _settle_slip_if_ready(slip_id: int) -> BetSlip:
    """Resolve an accumulator once none of its legs are still pending. Any lost
    leg loses the slip; otherwise it wins and pays stake x (product of won-leg
    odds, void legs counting as 1.0). Payout credit is idempotency-keyed."""
    slip = BetSlip.objects.select_for_update().get(pk=slip_id)
    if slip.status not in (BetSlip.Status.OPEN, BetSlip.Status.PENDING):
        return slip  # already settled — idempotent

    legs = list(slip.legs.all())
    if any(leg.result == BetLeg.Result.PENDING for leg in legs):
        return slip  # not all legs resolved yet

    if any(leg.result == BetLeg.Result.LOST for leg in legs):
        slip.status = BetSlip.Status.LOST
    else:
        effective = Decimal('1')
        for leg in legs:
            if leg.result == BetLeg.Result.WON:
                effective *= leg.odds
        payout = utils.calculate_payout(slip.stake, effective)
        if slip.player_id:
            wallet_services.credit(
                player_id=slip.player_id, amount=payout, kind='bet_payout',
                idempotency_key=helpers.slip_payout_idempotency_key(slip.id),
                reference=f'slip:{slip.id}',
            )
        slip.payout = payout
        slip.status = BetSlip.Status.WON

    slip.settled_at = timezone.now()
    slip.save(update_fields=['status', 'payout', 'settled_at'])
    return slip


# -- external provider sync (api-football) -----------------------------------

def _upsert_team(info: Optional[TeamInfo]) -> Optional[Team]:
    if info is None or not info.external_id:
        return None
    team, _ = Team.objects.update_or_create(
        provider=ApiFootballClient.provider_name, external_id=info.external_id,
        defaults={'name': info.name, 'logo_url': info.logo_url},
    )
    return team


@transaction.atomic
def sync_fixture(fixture: FixtureUpdate) -> Optional[Event]:
    """Apply one api-football fixture update to its linked Event: upsert the
    Team records, lock betting once the match goes live, and settle every
    bet/leg on it once finished.

    No-op (returns None) if no Event is linked to this fixture's external_id.
    """
    event = (
        Event.objects.select_for_update()
        .filter(external_id=fixture.external_id, provider=ApiFootballClient.provider_name)
        .first()
    )
    if event is None:
        return None

    update_fields = []
    home_team = _upsert_team(fixture.home_team)
    if home_team is not None and event.home_team_id != home_team.id:
        event.home_team = home_team
        update_fields.append('home_team')
    away_team = _upsert_team(fixture.away_team)
    if away_team is not None and event.away_team_id != away_team.id:
        event.away_team = away_team
        update_fields.append('away_team')
    if (fixture.is_live or fixture.is_finished) and event.is_open:
        event.is_open = False
        update_fields.append('is_open')
    if update_fields:
        event.save(update_fields=update_fields)

    result = fixture.result
    if result is not None:
        settle_event(event.id, result)

    return event


def sync_provider_fixtures(*, date: Optional[str] = None, live: Optional[str] = None) -> int:
    """Pull fixtures from api-football and sync each linked Event. Returns the
    number of fixtures fetched (not all are necessarily linked to an Event)."""
    client = ApiFootballClient()
    fixtures = client.fetch_fixtures(date=date, live=live)
    for fixture in fixtures:
        sync_fixture(fixture)
    return len(fixtures)


@transaction.atomic
def sync_fixture_odds(odds: OddsSnapshot) -> Optional[Event]:
    """Apply a 1X2 odds snapshot to its linked, still-open Event. No-op if
    unlinked or betting is already closed (avoids moving a locked price)."""
    event = (
        Event.objects.select_for_update()
        .filter(
            external_id=odds.external_id, provider=ApiFootballClient.provider_name, is_open=True,
        )
        .first()
    )
    if event is None:
        return None
    event.odds = odds.odds_home
    event.odds_draw = odds.odds_draw
    event.odds_away = odds.odds_away
    event.save(update_fields=['odds', 'odds_draw', 'odds_away', 'previous_odds'])
    return event


def sync_provider_odds(*, date: Optional[str] = None) -> int:
    """Pull 1X2 odds from api-football and apply each to its linked Event.
    Returns the number of odds snapshots fetched."""
    client = ApiFootballClient()
    snapshots = client.fetch_odds(date=date)
    for snapshot in snapshots:
        sync_fixture_odds(snapshot)
    return len(snapshots)


# -- realtime ----------------------------------------------------------------

def publish_event_odds(event: Event) -> None:
    """Push an event's current prices to its realtime channel so open bet slips
    update live. Best-effort: the publisher is a no-op unless realtime is
    enabled, and never raises into the caller."""
    import json

    from apps.livechat.clients import RealtimePublisherClient

    snapshot = json.dumps({
        'event_id': event.id,
        'name': event.name,
        'odds': str(event.odds),
        'odds_draw': str(event.odds_draw) if event.odds_draw is not None else None,
        'odds_away': str(event.odds_away) if event.odds_away is not None else None,
    })
    client = RealtimePublisherClient()
    try:
        client.publish(f'odds:{event.id}', snapshot)
        # Also feed the global live-odds ticker with a compact human line.
        client.publish('odds', f'{event.name}: {event.odds}')
    except Exception:  # noqa: BLE001 — realtime must never break a save
        pass
