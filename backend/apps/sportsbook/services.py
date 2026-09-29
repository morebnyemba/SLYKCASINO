"""sportsbook domain logic — the ONLY place sportsbook mutations happen.

Bet placement debits the wallet via wallet.services (cross-context, by ID), and
settlement credits payouts. Both use deterministic idempotency keys so retries
and recovery never double-charge or double-pay.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

import logging

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.wallet import services as wallet_services

from . import helpers, utils
from .clients import (
    ApiFootballClient, FeedMarketData, FixtureUpdate, LiveOddsSnapshot, OddsSnapshot, TeamInfo,
)
from .dtos import BetDTO
from .models import (
    Bet, BetLeg, BetSlip, Event, LeagueSetting, Market, MarketOutcome, Selection, Team,
)
from .settlement import GoalEvent, Score, settle_outcome


logger = logging.getLogger(__name__)


class OddsChanged(ValueError):
    """The price a player saw no longer matches the current price."""

    def __init__(
        self, label: str, expected: Decimal, current: Decimal, outcome_id: Optional[int] = None,
        *, event_id: Optional[int] = None, selection: Optional[str] = None,
    ):
        self.current = current
        self.outcome_id = outcome_id
        # Set for a 1X2 pick (no outcome row), so the slip can find the leg.
        self.event_id = event_id
        self.selection = selection
        super().__init__(f'Odds for {label} changed from {expected} to {current}.')


class SelectionUnavailable(ValueError):
    """The market/outcome is suspended, settled, or the event is closed."""


# -- reads -------------------------------------------------------------------

# Provider statuses meaning the match is in play (betting closed, still shown).
LIVE_STATUSES = ('1H', 'HT', '2H', 'ET', 'BT', 'P', 'SUSP', 'INT', 'LIVE')


def list_events(
    *, featured: Optional[bool] = None, sport: Optional[str] = None,
    upcoming: bool = False, priced: Optional[bool] = None,
):
    """Events for listings. `upcoming` keeps what a player can still bet on or
    follow — open matches that haven't long kicked off, plus matches in play —
    ordered by kick-off (soonest first). `priced` filters on whether real odds
    have arrived."""
    from datetime import timedelta
    from django.db.models import F, Q

    qs = Event.objects.all()
    if featured:
        qs = qs.filter(featured=True)
    if sport:
        qs = qs.filter(sport=sport)
    if priced is not None:
        qs = qs.filter(has_odds=priced)
    if upcoming:
        recent = timezone.now() - timedelta(hours=3)
        qs = qs.filter(
            Q(is_open=True, starts_at__gte=recent) | Q(is_open=True, starts_at__isnull=True)
            | Q(status__in=LIVE_STATUSES),
        ).order_by(F('starts_at').asc(nulls_last=True), 'name', 'id')
    return qs


def _outcome_for(selection: str, result: str) -> str:
    """Map a wager's backed selection against the event result to a settle outcome."""
    if result == 'void':
        return 'void'
    return 'won' if selection == result else 'lost'


def to_dto(bet: Bet) -> BetDTO:
    return BetDTO.model_validate(bet)


# -- mutations ---------------------------------------------------------------

def _kicked_off(starts_at) -> bool:
    """Pre-match betting closes at the scheduled kick-off, even before the live
    poll has marked the event closed."""
    return starts_at is not None and starts_at <= timezone.now()


# -- in-play -------------------------------------------------------------------

# Statuses we trade in play. Markets settle on the 90 minutes, so extra time and
# penalties (ET/BT/P) are not traded, nor interrupted/suspended matches.
IN_PLAY_STATUSES = ('1H', 'HT', '2H')


def live_betting_enabled() -> bool:
    from django.conf import settings
    return bool(getattr(settings, 'SPORTSBOOK_LIVE_BETTING', False))


def _live_setting(name: str, default: int) -> int:
    from django.conf import settings
    return int(getattr(settings, name, default))


def in_play_bettable(event: Event, *, now=None) -> bool:
    """Whether `event` is trading in play right now: live betting is on, the
    match is in a traded period, an operator hasn't closed it, and the live feed
    priced it within the last SPORTSBOOK_LIVE_ODDS_STALE seconds (a feed that
    goes quiet suspends betting rather than leaving stale prices up)."""
    from datetime import timedelta

    if not live_betting_enabled() or not event.is_open or event.status not in IN_PLAY_STATUSES:
        return False
    if event.live_odds_at is None:
        return False
    now = now or timezone.now()
    return event.live_odds_at >= now - timedelta(seconds=_live_setting('SPORTSBOOK_LIVE_ODDS_STALE', 30))


def _started(event: Event) -> bool:
    return _kicked_off(event.starts_at) or event.status in LIVE_STATUSES


def pre_match_bettable(event: Event) -> bool:
    return event.is_open and event.has_odds and not _started(event)


def trading_state(event: Event, *, now=None) -> dict:
    """What a player can back right now: `in_play` (trading live), `bettable`
    (the event takes bets at all) and `main_open` (the 1X2 buttons are live)."""
    live = in_play_bettable(event, now=now)
    return {
        'in_play': live,
        'bettable': live or pre_match_bettable(event),
        'main_open': (live and event.live_main_open) or pre_match_bettable(event),
    }


def _main_price(event: Event, selection: str) -> Optional[Decimal]:
    return {
        Selection.HOME: event.odds, Selection.DRAW: event.odds_draw, Selection.AWAY: event.odds_away,
    }.get(selection)


def _check_event_bettable(event_id: int, selection: str = Selection.HOME, odds: Optional[Decimal] = None) -> bool:
    """A 1X2 pick needs a real price and open betting. Pre-match closes at
    kick-off; after that only an in-play event takes bets, at the live price
    (OddsChanged if it moved). Returns True for an in-play pick."""
    event = Event.objects.filter(pk=event_id).first()
    if event is None:
        return False  # soft link to a missing event: legacy behaviour, label-only bet
    if _started(event):
        if not in_play_bettable(event):
            raise SelectionUnavailable(f'Betting on {event.name} is closed.')
        current = _main_price(event, selection)
        if not event.live_main_open or current is None:
            raise SelectionUnavailable(f'{event.name} — match result is suspended.')
        if odds is not None and utils.quantize(odds) != utils.quantize(current):
            raise OddsChanged(
                f'{event.name} — {selection}', utils.quantize(odds), current,
                event_id=event.id, selection=selection,
            )
        return True
    if not event.has_odds:
        raise SelectionUnavailable(f'{event.name} has no odds yet.')
    if not event.is_open:
        raise SelectionUnavailable(f'Betting on {event.name} is closed.')
    return False


def _lock_bettable_outcome(outcome_id: int, odds: Decimal) -> tuple[MarketOutcome, bool]:
    """Row-lock an outcome and check it can be backed at `odds` right now.
    Returns (outcome, in_play)."""
    try:
        outcome = (
            MarketOutcome.objects.select_for_update()
            .select_related('market', 'market__event')
            .get(pk=outcome_id)
        )
    except MarketOutcome.DoesNotExist as exc:
        raise SelectionUnavailable('That selection no longer exists.') from exc
    market, event = outcome.market, outcome.market.event
    in_play = _started(event)
    event_ok = in_play_bettable(event) if in_play else event.is_open
    if (
        not event_ok or not market.is_open or market.settled
        or not outcome.is_open or outcome.result != MarketOutcome.Result.PENDING
    ):
        raise SelectionUnavailable(f'{market.name} — {outcome.label} is suspended.')
    if utils.quantize(odds) != utils.quantize(outcome.odds):
        raise OddsChanged(f'{market.name} — {outcome.label}', utils.quantize(odds), outcome.odds, outcome.id)
    return outcome, in_play


def _schedule_confirmation(kind: str, obj_id: int) -> None:
    """Confirm an in-play bet once the acceptance delay has passed. The live-odds
    sweep (confirm_accepting_bets) also picks it up, so a lost task only delays it.
    Sent from a background thread: a slow or unreachable broker must never hold
    up the player's response."""
    import threading

    def send():
        try:
            from .tasks import confirm_live_bet
            confirm_live_bet.apply_async(
                args=(kind, obj_id), countdown=_live_setting('SPORTSBOOK_LIVE_BET_DELAY', 6), retry=False,
            )
        except Exception:  # noqa: BLE001 — broker down: the sweep confirms it instead
            logger.warning('could not schedule in-play confirmation for %s %s', kind, obj_id, exc_info=True)

    transaction.on_commit(lambda: threading.Thread(target=send, daemon=True).start())


@transaction.atomic
def place_bet(
    *, event: str, stake: Decimal, odds: Decimal, player_id: Optional[int] = None,
    event_id: Optional[int] = None, selection: str = Selection.HOME,
    outcome_id: Optional[int] = None,
) -> Bet:
    """Place a bet. For an identified player the stake is debited from the wallet
    atomically; raising InsufficientFunds rolls the whole placement back.

    `event_id`/`selection` soft-link the bet to its market so a single result can
    settle every bet on it (see settle_event). `outcome_id` instead backs an
    outcome of a secondary market (goals, handicaps…); its live price is checked
    and OddsChanged is raised if the player's price is stale."""
    errors = helpers.validate_bet_request_structure({'event': event, 'stake': stake, 'odds': odds})
    if errors:
        raise ValueError('; '.join(errors))
    if selection not in Selection.values:
        selection = Selection.HOME
    outcome = None
    in_play = False
    if outcome_id is not None:
        outcome, in_play = _lock_bettable_outcome(outcome_id, Decimal(str(odds)))
        event_id = outcome.market.event_id
        selection = Selection.HOME
    elif event_id is not None:
        in_play = _check_event_bettable(event_id, selection, Decimal(str(odds)))
    # In-play bets hold the stake through an acceptance delay (confirm_live_bet).
    placed_status = Bet.Status.ACCEPTING if in_play else Bet.Status.OPEN

    if player_id is None:
        # Anonymous compatibility path — no wallet movement (documented).
        bet = Bet.objects.create(
            event=event, stake=utils.quantize(stake), odds=odds, status=placed_status,
            event_ref_id=event_id, selection=selection, outcome_ref=outcome,
        )
        if in_play:
            _schedule_confirmation('bet', bet.id)
        return bet

    # Record intent as PENDING, debit the stake, then mark OPEN.
    bet = Bet.objects.create(
        player_id=player_id, event=event, stake=utils.quantize(stake),
        odds=odds, status=Bet.Status.PENDING, event_ref_id=event_id, selection=selection,
        outcome_ref=outcome,
    )
    wallet_services.debit(
        player_id=player_id, amount=bet.stake, kind='bet_stake',
        idempotency_key=helpers.stake_idempotency_key(bet.id), reference=f'bet:{bet.id}',
    )
    bet.status = placed_status
    bet.save(update_fields=['status'])
    if in_play:
        _schedule_confirmation('bet', bet.id)
    return bet


@transaction.atomic
def settle_event(event_id: int, result: str) -> int:
    """Settle every open bet linked to an event from a single result.

    `result` is one of 'home' | 'draw' | 'away' | 'void'. Each bet is won/lost by
    comparing its backed selection; settlement is delegated to settle_bet so wallet
    payouts stay idempotent. Returns the number of bets settled."""
    if result not in (*Selection.values, 'void'):
        raise ValueError("result must be 'home', 'draw', 'away', or 'void'")

    # Secondary-market bets (outcome_ref set) settle per outcome, not by 1X2.
    bets = Bet.objects.filter(
        event_ref_id=event_id, outcome_ref__isnull=True,
        status__in=(Bet.Status.OPEN, Bet.Status.PENDING),
    ).values_list('id', 'selection')
    settled = 0
    for bet_id, selection in list(bets):
        settle_bet(bet_id, _outcome_for(selection, result))
        settled += 1

    # Resolve any accumulator legs on this event, then re-check their parent slips.
    legs = BetLeg.objects.filter(
        event_ref_id=event_id, outcome_ref__isnull=True, result=BetLeg.Result.PENDING,
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

    if result == 'void':
        # A void (abandoned/cancelled) event voids every market on it too.
        for market in Market.objects.filter(event_id=event_id, settled=False):
            settled += _settle_market(market, {o.id: 'void' for o in market.outcomes.all()})

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
    player, rolling back atomically on InsufficientFunds. A leg may carry
    `outcome_id` to back a secondary-market outcome (price-checked); at most one
    leg per event is allowed."""
    if not legs or len(legs) < 2:
        raise ValueError('an accumulator needs at least 2 selections')

    combined = Decimal('1')
    normalised: list[dict] = []
    seen_events: set[int] = set()
    in_play = False
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
        event_id = leg.get('event_id')
        outcome = None
        leg_in_play = False
        if leg.get('outcome_id') is not None:
            outcome, leg_in_play = _lock_bettable_outcome(int(leg['outcome_id']), odds)
            event_id = outcome.market.event_id
            selection = Selection.HOME
        elif event_id is not None:
            leg_in_play = _check_event_bettable(event_id, selection, odds)
        in_play = in_play or leg_in_play
        # Selections on the same event are correlated, so a multiple takes one per event.
        if event_id is not None:
            if int(event_id) in seen_events:
                raise ValueError('an accumulator can include only one selection per event')
            seen_events.add(int(event_id))
        combined *= odds
        normalised.append({
            'event': leg['event'], 'odds': odds, 'selection': selection,
            'event_id': event_id, 'outcome': outcome,
        })
    combined_odds = utils.quantize(combined)

    placed_status = BetSlip.Status.ACCEPTING if in_play else BetSlip.Status.OPEN
    status_ = placed_status if player_id is None else BetSlip.Status.PENDING
    slip = BetSlip.objects.create(
        player_id=player_id, stake=utils.quantize(stake),
        combined_odds=combined_odds, status=status_,
    )
    BetLeg.objects.bulk_create([
        BetLeg(slip=slip, event=n['event'], odds=n['odds'], selection=n['selection'],
               event_ref_id=n['event_id'], outcome_ref=n['outcome'])
        for n in normalised
    ])

    if player_id is not None:
        wallet_services.debit(
            player_id=player_id, amount=slip.stake, kind='bet_stake',
            idempotency_key=helpers.slip_stake_idempotency_key(slip.id), reference=f'slip:{slip.id}',
        )
        slip.status = placed_status
        slip.save(update_fields=['status'])
    if in_play:
        _schedule_confirmation('slip', slip.id)
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


# -- in-play acceptance ---------------------------------------------------------

_WAIT = 'wait'


def _live_recheck(
    *, event_id: Optional[int], selection: str, outcome_id: Optional[int], odds: Decimal, placed_at, now,
) -> Optional[str]:
    """Re-check one in-play pick after the acceptance delay. None = it stands,
    _WAIT = the feed hasn't refreshed since the bet was struck, else the reason
    it's rejected: a goal since placement, a suspension, or a price move."""
    if event_id is None:
        return None
    event = Event.objects.filter(pk=event_id).first()
    if event is None:
        return 'the match is no longer available'
    if not _started(event):
        return None  # a pre-match leg in an in-play multiple — already accepted
    if event.last_goal_at is not None and event.last_goal_at >= placed_at:
        return 'the score changed'
    if not in_play_bettable(event, now=now):
        return 'betting was suspended'
    if outcome_id is not None:
        outcome = MarketOutcome.objects.select_related('market').filter(pk=outcome_id).first()
        if (
            outcome is None or not outcome.market.is_open or outcome.market.settled
            or not outcome.is_open or outcome.result != MarketOutcome.Result.PENDING
        ):
            return 'the selection was suspended'
        current = outcome.odds
    else:
        current = _main_price(event, selection) if event.live_main_open else None
        if current is None:
            return 'the selection was suspended'
    if utils.quantize(current) != utils.quantize(odds):
        return 'the price changed'
    if event.live_odds_at <= placed_at:
        return _WAIT
    return None


def _reject_accepting(obj, reason: str, *, now) -> None:
    """Refund the held stake and mark an in-play bet/slip REJECTED."""
    is_slip = isinstance(obj, BetSlip)
    if obj.player_id:
        key = helpers.slip_payout_idempotency_key(obj.id) if is_slip else helpers.payout_idempotency_key(obj.id)
        wallet_services.credit(
            player_id=obj.player_id, amount=obj.stake, kind='bet_payout',
            idempotency_key=f'{key}:refund', reference=f'{"slip" if is_slip else "bet"}:{obj.id}',
        )
    obj.status = obj.Status.REJECTED
    obj.settled_at = now
    obj.save(update_fields=['status', 'settled_at'])
    if obj.player_id:
        from apps.notifications import services as notif_services
        notif_services.notify(
            player_id=obj.player_id, kind='account_alert', title='In-play bet not accepted',
            body=f'Your {"multiple" if is_slip else "bet"} #{obj.id} was not accepted because {reason}. '
                 'Your stake has been refunded.',
        )


@transaction.atomic
def confirm_live_bet(kind: str, obj_id: int, *, now=None) -> str:
    """Accept or reject an in-play bet ('bet') or multiple ('slip') once the
    acceptance delay has passed: every in-play pick must still be trading at the
    price taken, with no goal since placement and a feed update after it.
    Idempotent; returns the resulting status (still ACCEPTING if it's too early
    or the feed hasn't refreshed yet)."""
    from datetime import timedelta

    now = now or timezone.now()
    model = BetSlip if kind == 'slip' else Bet
    obj = model.objects.select_for_update().filter(pk=obj_id).first()
    if obj is None:
        return ''
    if obj.status != model.Status.ACCEPTING:
        return obj.status
    delay = timedelta(seconds=_live_setting('SPORTSBOOK_LIVE_BET_DELAY', 6))
    if now - obj.placed_at < delay:
        return obj.status

    if model is Bet:
        picks = [(obj.event_ref_id, obj.selection, obj.outcome_ref_id, obj.odds)]
    else:
        picks = [(leg.event_ref_id, leg.selection, leg.outcome_ref_id, leg.odds) for leg in obj.legs.all()]
    reasons = [
        _live_recheck(event_id=e, selection=sel, outcome_id=o, odds=odds, placed_at=obj.placed_at, now=now)
        for e, sel, o, odds in picks
    ]
    reason = next((r for r in reasons if r not in (None, _WAIT)), None)
    if reason is None and _WAIT in reasons:
        stale = timedelta(seconds=_live_setting('SPORTSBOOK_LIVE_ODDS_STALE', 30))
        if now - obj.placed_at < delay + stale:
            return obj.status
        reason = 'the live price could not be confirmed'
    if reason is not None:
        _reject_accepting(obj, reason, now=now)
        return obj.status
    obj.status = model.Status.OPEN
    obj.save(update_fields=['status'])
    return obj.status


def confirm_accepting_bets(*, now=None) -> int:
    """Sweep in-play bets past their acceptance delay (the per-bet task is the
    fast path; this catches any it missed). Returns how many were resolved."""
    from datetime import timedelta

    now = now or timezone.now()
    cutoff = now - timedelta(seconds=_live_setting('SPORTSBOOK_LIVE_BET_DELAY', 6))
    resolved = 0
    for kind, model in (('bet', Bet), ('slip', BetSlip)):
        ids = model.objects.filter(status=model.Status.ACCEPTING, placed_at__lte=cutoff).values_list('id', flat=True)
        for obj_id in list(ids):
            if confirm_live_bet(kind, obj_id, now=now) != model.Status.ACCEPTING:
                resolved += 1
    return resolved


# -- secondary markets ---------------------------------------------------------

_LEG_RESULT = {'won': BetLeg.Result.WON, 'lost': BetLeg.Result.LOST, 'void': BetLeg.Result.VOID}


def list_markets(event_id: int):
    """Every market on an event with its outcomes, in display order."""
    return Market.objects.filter(event_id=event_id).prefetch_related('outcomes')


@transaction.atomic
def _settle_market(market: Market, results: dict[int, str]) -> int:
    """Apply outcome results ({outcome_id: 'won'|'lost'|'void'}) to a market and
    settle every bet/accumulator leg backing those outcomes. Outcomes missing
    from `results` stay pending (and so does the market). Idempotent: already
    settled bets are skipped by settle_bet's status guard. Returns bets settled."""
    settled = 0
    slips: set[int] = set()
    for outcome in market.outcomes.all():
        result = results.get(outcome.id)
        if result not in ('won', 'lost', 'void'):
            continue
        if outcome.result != result:
            outcome.result = result
            outcome.is_open = False
            outcome.save(update_fields=['result', 'is_open'])
        bet_ids = Bet.objects.filter(
            outcome_ref=outcome, status__in=(Bet.Status.OPEN, Bet.Status.PENDING),
        ).values_list('id', flat=True)
        for bet_id in list(bet_ids):
            settle_bet(bet_id, result)
            settled += 1
        for leg in BetLeg.objects.filter(outcome_ref=outcome, result=BetLeg.Result.PENDING):
            leg.result = _LEG_RESULT[result]
            leg.save(update_fields=['result'])
            slips.add(leg.slip_id)
    for slip_id in slips:
        _settle_slip_if_ready(slip_id)

    if not market.outcomes.filter(result=MarketOutcome.Result.PENDING).exists():
        market.settled = True
        market.is_open = False
        market.needs_review = False
        market.save(update_fields=['settled', 'is_open', 'needs_review'])
    return settled


def score_for_event(event: Event) -> Optional[Score]:
    """Everything known about a finished event's outcome, for settlement: the
    90-minute score plus any stored match facts (corners, cards, goal events,
    participants). None until the score is known."""
    if event.score_home is None or event.score_away is None:
        return None
    facts = event.match_facts or {}

    def pair(key):
        value = facts.get(key)
        return (int(value[0]), int(value[1])) if isinstance(value, list) and len(value) == 2 else None

    goals = None
    if isinstance(facts.get('goals'), list):
        events = [
            GoalEvent(
                minute=int(g.get('minute') or 0), side=str(g.get('side')), player=str(g.get('player') or ''),
                own_goal=bool(g.get('own_goal')), penalty=bool(g.get('penalty')),
            )
            for g in facts['goals']
        ]
        goals = tuple(events)
        tally = (sum(g.side == 'home' for g in goals), sum(g.side == 'away' for g in goals))
        if tally != (event.score_home, event.score_away):
            # Feeds differ on which team an own goal is listed under; try the other way.
            flip = {'home': 'away', 'away': 'home'}
            flipped = tuple(
                GoalEvent(g.minute, flip.get(g.side, g.side), g.player, g.own_goal, g.penalty) if g.own_goal else g
                for g in goals
            )
            if (sum(g.side == 'home' for g in flipped), sum(g.side == 'away' for g in flipped)) == (
                event.score_home, event.score_away,
            ):
                goals = flipped

    yellow, red = pair('yellow'), pair('red')
    participants = facts.get('participants')
    return Score(
        home=event.score_home, away=event.score_away,
        ht_home=event.ht_score_home, ht_away=event.ht_score_away,
        corners=pair('corners'),
        cards=(yellow[0] + red[0], yellow[1] + red[1]) if yellow and red else None,
        reds=red,
        goals=goals,
        participants=tuple(participants) if isinstance(participants, list) else None,
        extra_time=bool(facts.get('extra_time')),
    )


def settle_event_markets(event_id: int, score: Score, *, final: bool = True) -> int:
    """Settle every market on an event that the match facts decide. Anything
    still undecided (stats not published yet, ambiguous player name, unknown bet
    type) stays pending and — when `final` — is flagged `needs_review` so it
    surfaces for an operator if a later retry can't settle it either.
    Returns the number of bets settled."""
    settled = 0
    for market in list_markets(event_id).filter(settled=False):
        results = {}
        for outcome in market.outcomes.all():
            result = settle_outcome(
                kind=market.kind, period=market.period, line=market.line, metric=market.metric,
                key=outcome.key, label=outcome.label, score=score,
            )
            if result is not None:
                results[outcome.id] = result
        if results:
            settled += _settle_market(market, results)
        market.refresh_from_db(fields=['settled'])
        if final and not market.settled and not market.needs_review:
            market.needs_review = True
            market.save(update_fields=['needs_review'])
    return settled


@transaction.atomic
def settle_market_manually(market_id: int, *, winners: list[int], void: bool = False) -> int:
    """Operator settlement for any market: the outcomes in `winners` win and the
    rest lose, or every outcome is voided with `void=True`. Returns bets settled."""
    market = Market.objects.select_for_update().get(pk=market_id)
    outcome_ids = list(market.outcomes.values_list('id', flat=True))
    unknown = set(winners) - set(outcome_ids)
    if unknown:
        raise ValueError(f'outcomes {sorted(unknown)} are not in this market')
    if not void and not winners:
        raise ValueError('pick at least one winning outcome, or void the market')
    results = {
        oid: 'void' if void else ('won' if oid in winners else 'lost') for oid in outcome_ids
    }
    return _settle_market(market, results)


@transaction.atomic
def settle_event_from_score(
    event_id: int, *, home: int, away: int,
    ht_home: Optional[int] = None, ht_away: Optional[int] = None,
    corners: Optional[tuple[int, int]] = None, yellow: Optional[tuple[int, int]] = None,
    red: Optional[tuple[int, int]] = None,
) -> int:
    """Operator settlement: record the final (90-minute) score — plus corner and
    card counts when given — and settle the 1X2 and every market those facts
    decide. Returns bets settled."""
    event = Event.objects.select_for_update().get(pk=event_id)
    event.score_home, event.score_away = home, away
    event.ht_score_home, event.ht_score_away = ht_home, ht_away
    event.status = 'FT'
    event.is_open = False
    facts = dict(event.match_facts or {})
    for key, value in (('corners', corners), ('yellow', yellow), ('red', red)):
        if value is not None:
            facts[key] = [int(value[0]), int(value[1])]
    event.match_facts = facts or None
    event.save(update_fields=[
        'score_home', 'score_away', 'ht_score_home', 'ht_score_away', 'status', 'is_open', 'match_facts',
    ])
    result = 'home' if home > away else 'away' if away > home else 'draw'
    settled = settle_event(event_id, result)
    settled += settle_event_markets(event_id, score_for_event(event))
    return settled


@transaction.atomic
def apply_feed_markets(event: Event, markets: tuple[FeedMarketData, ...] | list[FeedMarketData]) -> int:
    """Upsert a feed's markets/outcomes onto an open event. Prices that move keep
    their previous price for the ▲/▼ hint; markets or outcomes the feed stopped
    offering are suspended (not deleted — bets may reference them). Settled
    markets are never touched. Returns the number of markets in the feed."""
    existing = {m.key: m for m in Market.objects.filter(event=event).prefetch_related('outcomes')}
    seen: set[str] = set()
    for data in markets:
        seen.add(data.key)
        market = existing.get(data.key)
        if market is None:
            market = Market.objects.create(
                event=event, key=data.key, name=data.name, group=data.group, kind=data.kind,
                period=data.period, line=data.line, sort_order=data.sort_order, metric=data.metric,
            )
            outcomes = {}
        else:
            if market.settled:
                continue
            changed = []
            for field in ('name', 'group', 'sort_order'):
                if getattr(market, field) != getattr(data, field):
                    setattr(market, field, getattr(data, field))
                    changed.append(field)
            if not market.is_open:
                market.is_open = True
                changed.append('is_open')
            if changed:
                market.save(update_fields=changed)
            outcomes = {o.key: o for o in market.outcomes.all()}

        feed_keys = set()
        for fo in data.outcomes:
            feed_keys.add(fo.key)
            outcome = outcomes.get(fo.key)
            if outcome is None:
                MarketOutcome.objects.create(
                    market=market, key=fo.key, label=fo.label, odds=fo.odds, sort_order=fo.sort_order,
                )
                continue
            changed = []
            if outcome.odds != fo.odds:
                outcome.previous_odds = outcome.odds
                outcome.odds = fo.odds
                changed += ['odds', 'previous_odds']
            if not outcome.is_open and outcome.result == MarketOutcome.Result.PENDING:
                outcome.is_open = True
                changed.append('is_open')
            if outcome.label != fo.label or outcome.sort_order != fo.sort_order:
                outcome.label, outcome.sort_order = fo.label, fo.sort_order
                changed += ['label', 'sort_order']
            if changed:
                outcome.save(update_fields=changed)
        for key, outcome in outcomes.items():
            if key not in feed_keys and outcome.is_open:
                outcome.is_open = False
                outcome.save(update_fields=['is_open'])

    for key, market in existing.items():
        if key not in seen and market.is_open and not market.settled:
            market.is_open = False
            market.save(update_fields=['is_open'])
    return len(seen)


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
    # Pre-match betting ends at kick-off; with live betting on, a match stays open
    # through the periods we trade in play (in_play_bettable gates the rest).
    trading_live = live_betting_enabled() and fixture.status in IN_PLAY_STATUSES
    if (fixture.is_finished or (fixture.is_live and not trading_live)) and event.is_open:
        event.is_open = False
        update_fields.append('is_open')
    # Live score/status for the scoreboard; regulation-time score once finished.
    home, away = fixture.regulation_score if fixture.is_finished else (fixture.goals_home, fixture.goals_away)
    live_fields = {
        'status': fixture.status[:8], 'elapsed': fixture.elapsed,
        'score_home': home, 'score_away': away,
        'ht_score_home': fixture.ht_home, 'ht_score_away': fixture.ht_away,
    }
    if fixture.facts is not None:
        live_fields['match_facts'] = fixture.facts
    update_fields += _note_goal(event, home, away)
    for field, value in live_fields.items():
        if getattr(event, field) != value:
            setattr(event, field, value)
            update_fields.append(field)
    if update_fields:
        event.save(update_fields=update_fields)

    result = fixture.result
    if result is not None:
        settle_event(event.id, result)
        # Stats-based markets (corners, cards, scorers) settle once the facts are
        # in; until then they stay pending and settle_finished_fixtures retries.
        settle_event_markets(event.id, score_for_event(event), final=fixture.facts is not None)

    return event


def _note_goal(event: Event, home, away, *, now=None) -> list[str]:
    """Stamp last_goal_at when a known score changes (a goal, or one ruled out),
    so in-play bets struck before the feed caught up are rejected."""
    if event.score_home is None or event.score_away is None or home is None or away is None:
        return []
    if (event.score_home, event.score_away) == (home, away):
        return []
    event.last_goal_at = now or timezone.now()
    return ['last_goal_at']


def sync_provider_fixtures(*, date: Optional[str] = None, live: Optional[str] = None) -> int:
    """Pull fixtures from api-football and sync each linked Event. Returns the
    number of fixtures fetched (not all are necessarily linked to an Event)."""
    client = ApiFootballClient()
    fixtures = client.fetch_fixtures(date=date, live=live)
    for fixture in fixtures:
        sync_fixture(fixture)
    return len(fixtures)


FINISHED_STATUSES = ('FT', 'AET', 'PEN')
# Void matches the provider says won't be played (cancelled/abandoned/awarded…).
VOID_STATUSES = ('CANC', 'ABD', 'AWD', 'WO')


def events_awaiting_settlement(*, now=None):
    """Provider-linked events that kicked off long enough ago to be over and
    still have something to settle: not yet marked finished, or finished with
    open bets/legs or unsettled markets. Bounded to the last few days so a
    fixture the feed never finalises doesn't get polled forever."""
    from datetime import timedelta
    from django.db.models import Q

    now = now or timezone.now()
    return Event.objects.filter(
        provider=ApiFootballClient.provider_name, external_id__isnull=False,
        starts_at__lte=now - timedelta(minutes=105), starts_at__gte=now - timedelta(days=4),
    ).filter(
        ~Q(status__in=FINISHED_STATUSES + VOID_STATUSES)
        | Q(markets__settled=False)
        | Q(bets__status__in=(Bet.Status.OPEN, Bet.Status.PENDING))
        | Q(legs__result=BetLeg.Result.PENDING)
    ).distinct()


def settle_finished_fixtures(*, now=None) -> int:
    """Poll the provider for recently-started fixtures and settle everything on
    the ones that have finished — 1X2, score markets, and (once the provider
    publishes them) corners, cards and goalscorer markets. Matches that end up
    cancelled/abandoned are voided. Safe to run repeatedly: settlement is
    idempotent. Returns the number of fixtures fetched."""
    events = list(events_awaiting_settlement(now=now).values_list('id', 'external_id'))
    if not events:
        return 0
    fixtures = ApiFootballClient().fetch_fixtures_by_ids([ext for _, ext in events])
    by_ext = {ext: eid for eid, ext in events}
    for fixture in fixtures:
        sync_fixture(fixture)
        if fixture.status in VOID_STATUSES and fixture.external_id in by_ext:
            settle_event(by_ext[fixture.external_id], 'void')
    return len(fixtures)


def _create_event_from_fixture(fixture: FixtureUpdate) -> Optional[Event]:
    """Create a new Event for a fixture that has no linked Event yet. No-op
    (returns None) if a linked Event already exists or the fixture is already
    finished (nothing left to bet on). Race-safe via the DB's unique
    constraint on (provider, external_id): a concurrent run that loses the
    race just gets None back, same as if the Event already existed. The
    create runs in its own savepoint so a lost race rolls back only the
    failed insert, not the whole import loop."""
    if not fixture.external_id or fixture.is_finished:
        return None
    existing = Event.objects.filter(
        external_id=fixture.external_id, provider=ApiFootballClient.provider_name,
    ).first()
    if existing is not None:
        return None
    home_team = _upsert_team(fixture.home_team)
    away_team = _upsert_team(fixture.away_team)
    try:
        with transaction.atomic():
            return Event.objects.create(
                name=fixture.name,
                sport=Event.Sport.FOOTBALL,
                external_id=fixture.external_id,
                provider=ApiFootballClient.provider_name,
                home_team=home_team,
                away_team=away_team,
                starts_at=fixture.starts_at,
                is_open=not fixture.is_live,
                # No real prices until the odds sync reaches this fixture.
                has_odds=False,
            )
    except IntegrityError:
        return None  # lost a race with a concurrent import — already created


def sync_provider_events(
    *, date: Optional[str] = None, league: Optional[int] = None,
    season: Optional[int] = None, next_count: Optional[int] = None,
) -> int:
    """Pull fixtures from api-football and create an Event for each one not
    already linked, so they become bettable/visible without manual entry.
    Returns the number of fixtures fetched (not all necessarily new)."""
    client = ApiFootballClient()
    fixtures = client.fetch_fixtures(date=date, league=league, season=season, next_count=next_count)
    for fixture in fixtures:
        _create_event_from_fixture(fixture)
    return len(fixtures)


def import_all_current_leagues(*, next_count: Optional[int] = None) -> int:
    """Auto-discover every league api-football currently has an active season
    for, then import each *enabled* one's upcoming fixtures as Events — used
    when no manual API_FOOTBALL_LEAGUES list is configured, so the sportsbook
    fills up without an operator having to curate league IDs by hand.

    Every discovered league is upserted into LeagueSetting (enabled=True by
    default on first sight, existing rows untouched so a prior disable
    sticks), then skipped before its /fixtures call if disabled — so turning
    a league off from Django admin also saves the API call, not just the
    sportsbook clutter. Costs one /fixtures call per still-enabled league
    (plus the /leagues call itself), so this can be API-quota-heavy on
    lower-tier api-football plans with many leagues all enabled — that
    trade-off is accepted in exchange for zero-config coverage. Returns the
    total number of fixtures fetched across all enabled leagues."""
    client = ApiFootballClient()
    leagues = client.fetch_leagues()
    total = 0
    for league in leagues:
        setting, _ = LeagueSetting.objects.get_or_create(
            provider=ApiFootballClient.provider_name, league_id=league.id,
            defaults={'name': league.name},
        )
        if setting.name != league.name and league.name:
            setting.name = league.name
            setting.save(update_fields=['name'])
        if not setting.enabled:
            continue
        total += sync_provider_events(league=league.id, season=league.season, next_count=next_count)
    return total


@transaction.atomic
def sync_fixture_odds(odds: OddsSnapshot) -> Optional[Event]:
    """Apply an odds snapshot (1X2 + every other market) to its linked,
    still-open Event. No-op if unlinked or betting is already closed (avoids
    moving a locked price)."""
    event = (
        Event.objects.select_for_update()
        .filter(
            external_id=odds.external_id, provider=ApiFootballClient.provider_name, is_open=True,
        )
        # In play, the live feed owns the prices.
        .exclude(status__in=LIVE_STATUSES).exclude(live_odds_at__isnull=False)
        .first()
    )
    if event is None:
        return None
    event.odds = odds.odds_home
    event.odds_draw = odds.odds_draw
    event.odds_away = odds.odds_away
    event.has_odds = True
    event.save(update_fields=['odds', 'odds_draw', 'odds_away', 'previous_odds', 'has_odds'])
    if odds.markets:
        apply_feed_markets(event, odds.markets)
        transaction.on_commit(lambda: publish_event_markets(event))
    return event


def sync_provider_odds(
    *, date: Optional[str] = None, league: Optional[int] = None, season: Optional[int] = None,
) -> int:
    """Pull odds from api-football (by date, or by league + season) and apply
    each to its linked Event. Returns the number of odds snapshots fetched."""
    client = ApiFootballClient()
    snapshots = client.fetch_odds(date=date, league=league, season=season)
    for snapshot in snapshots:
        sync_fixture_odds(snapshot)
    return len(snapshots)


def sync_upcoming_odds() -> int:
    """Refresh odds for the fixtures players can bet on. With API_FOOTBALL_LEAGUES
    configured, pulls each league's odds (every upcoming fixture api-football
    prices, a page or two per league); otherwise pulls by date for today and the
    next API_FOOTBALL_ODDS_DAYS days. Returns the number of snapshots fetched."""
    from datetime import timedelta
    from django.conf import settings

    leagues = getattr(settings, 'API_FOOTBALL_LEAGUES', [])
    if leagues:
        season = getattr(settings, 'API_FOOTBALL_SEASON', None)
        return sum(sync_provider_odds(league=league, season=season) for league in leagues)
    days = int(getattr(settings, 'API_FOOTBALL_ODDS_DAYS', 2))
    today = timezone.localdate()
    return sum(
        sync_provider_odds(date=(today + timedelta(days=d)).isoformat()) for d in range(days + 1)
    )


# Live feed status names -> the fixtures feed's short codes.
_LIVE_STATUS_CODES = {'first half': '1H', 'halftime': 'HT', 'half time': 'HT', 'second half': '2H'}


@transaction.atomic
def apply_live_odds(snapshot: LiveOddsSnapshot, *, now=None) -> Optional[Event]:
    """Apply one fixture from the live odds feed: score/clock, the in-play 1X2 and
    markets, and the trading state. A blocked/stopped feed, or a match outside
    the traded periods, suspends in-play betting until the feed resumes."""
    event = (
        Event.objects.select_for_update()
        .filter(external_id=snapshot.external_id, provider=ApiFootballClient.provider_name)
        .first()
    )
    if event is None:
        return None
    now = now or timezone.now()
    fields: list[str] = []
    fields += _note_goal(event, snapshot.goals_home, snapshot.goals_away, now=now)
    code = _LIVE_STATUS_CODES.get((snapshot.status or '').strip().lower())
    updates = {
        'score_home': snapshot.goals_home, 'score_away': snapshot.goals_away,
        'elapsed': snapshot.elapsed,
        # The live feed is fresher than the minute-by-minute fixtures poll, but
        # never overrides a finished/void status.
        'status': code if code and event.status not in (*FINISHED_STATUSES, *VOID_STATUSES) else None,
    }
    for field, value in updates.items():
        if value is not None and getattr(event, field) != value:
            setattr(event, field, value)
            fields.append(field)

    tradable = not snapshot.blocked and event.is_open and event.status in IN_PLAY_STATUSES
    if not tradable:
        if event.live_odds_at is not None or event.live_main_open:
            event.live_odds_at, event.live_main_open = None, False
            fields += ['live_odds_at', 'live_main_open']
        if fields:
            event.save(update_fields=sorted(set(fields)))
            transaction.on_commit(lambda: publish_event_odds(event))
        return event

    if snapshot.one_x_two is not None:
        event.odds, event.odds_draw, event.odds_away = snapshot.one_x_two
        event.has_odds = True
        fields += ['odds', 'odds_draw', 'odds_away', 'previous_odds', 'has_odds']
    event.live_main_open = snapshot.one_x_two is not None
    event.live_odds_at = now
    fields += ['live_main_open', 'live_odds_at']
    event.save(update_fields=sorted(set(fields)))
    # Everything the live feed doesn't offer right now is suspended.
    apply_feed_markets(event, snapshot.markets)
    transaction.on_commit(lambda: (publish_event_odds(event), publish_event_markets(event)))
    return event


def sync_live_odds(*, now=None) -> int:
    """Poll api-football's in-play odds and apply them. Skips the call (saving
    quota) unless live betting is on and some linked match could be in play.
    Returns the number of live fixtures fetched."""
    from datetime import timedelta
    from django.db.models import Q

    if not live_betting_enabled():
        return 0
    now = now or timezone.now()
    maybe_live = Event.objects.filter(
        provider=ApiFootballClient.provider_name, external_id__isnull=False,
    ).filter(
        Q(status__in=IN_PLAY_STATUSES)
        | Q(starts_at__gte=now - timedelta(hours=3), starts_at__lte=now + timedelta(minutes=5))
        & ~Q(status__in=(*FINISHED_STATUSES, *VOID_STATUSES)),
    ).exists()
    if not maybe_live:
        return 0
    snapshots = ApiFootballClient().fetch_live_odds()
    for snapshot in snapshots:
        apply_live_odds(snapshot, now=now)
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
        **trading_state(event),
        'score_home': event.score_home, 'score_away': event.score_away,
        'elapsed': event.elapsed, 'status': event.status,
    })
    client = RealtimePublisherClient()
    try:
        client.publish(f'odds:{event.id}', snapshot)
        # Also feed the global live-odds ticker with a compact human line.
        client.publish('odds', f'{event.name}: {event.odds}')
    except Exception:  # noqa: BLE001 — realtime must never break a save
        pass


def publish_event_markets(event: Event) -> None:
    """Push an event's secondary-market prices to its realtime channel
    (`odds:<id>`, as a `type: markets` frame) so the event page updates live."""
    import json

    from apps.livechat.clients import RealtimePublisherClient

    payload = json.dumps({
        'type': 'markets',
        'event_id': event.id,
        'markets': [
            {
                'id': m.id, 'is_open': m.is_open,
                'outcomes': [
                    {'id': o.id, 'odds': str(o.odds), 'is_open': o.is_open} for o in m.outcomes.all()
                ],
            }
            for m in list_markets(event.id)
        ],
    })
    try:
        RealtimePublisherClient().publish(f'odds:{event.id}', payload)
    except Exception:  # noqa: BLE001 — realtime must never break a sync
        pass
