"""In-play market protection. Every automatic part is OFF by default — markets
stay open unless the feed or staff genuinely suspend them — and each can be
switched on in LiveTradingSettings.

- **Lock:** a match stops trading in play for good once its clock reaches
  LiveTradingSettings.lock_minute (75' by default). By the match clock, not
  the wall clock: half-time doesn't count. Set once and never cleared, so a
  feed that later reports an earlier minute can't reopen it. If the feed goes
  silent the clock can't be read, so a wall-clock cut-off (kick-off + lock
  minute + a half-time and stoppage allowance) locks the match anyway.
- **Hold:** a match is suspended for review when the feed looks wrong or the
  market looks attacked — a match-result price jumping with no goal, the score
  going down or the clock going backwards, or a burst of in-play money on one
  selection. Staff can also suspend by hand. Only staff reopen a hold.

While LiveTradingSettings.keep_markets_open is on (the default) the
automatic holds are disabled: nothing suspends a market before the lock
minute except staff, and what play has already decided (outcome_decided).

Either one makes services.in_play_bettable() false, so new in-play bets are
refused and bets still in their acceptance delay are rejected and refunded.
"""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from typing import Optional

from django.db.models import Q, Sum
from django.utils import timezone

from .models import Bet, BetLeg, BetSlip, Event, LiveTradingSettings

# A goal this recent explains a big price move.
GOAL_GRACE = timedelta(minutes=2)
# The feed's clock may wobble by a minute; more than this backwards is wrong.
CLOCK_SLACK = 2


# Half-time (15') plus stoppage-time allowance after the lock minute, for the
# wall-clock cut-off used only when the feed's match clock can't be read.
WALL_CLOCK_ALLOWANCE = timedelta(minutes=18)


def keep_markets_open() -> bool:
    return LiveTradingSettings.load().keep_markets_open


def wall_clock_locked(event: Event, *, now=None) -> bool:
    """Past the lock by the wall clock alone — the safety net for a silent
    feed. A healthy feed locks at the real lock minute, earlier than this."""
    minute = LiveTradingSettings.current().lock_minute
    if not minute or event.starts_at is None:
        return False
    return (now or timezone.now()) >= event.starts_at + timedelta(minutes=minute) + WALL_CLOCK_ALLOWANCE


def closed_reason(event: Event, *, now=None) -> Optional[str]:
    """Why in-play trading is shut on this match (None = it isn't)."""
    if event.live_locked_at or wall_clock_locked(event, now=now):
        minute = LiveTradingSettings.load().lock_minute
        return f'In-play betting closes at {minute}\''
    if event.live_hold_reason:
        return 'In-play betting is suspended'
    return None


def check_clock(event: Event, *, now=None) -> list[str]:
    """Lock the match if its clock has reached the lock minute. Returns the
    fields changed (the caller saves)."""
    from .services import IN_PLAY_STATUSES
    if event.live_locked_at or event.elapsed is None or event.status not in IN_PLAY_STATUSES:
        return []
    minute = LiveTradingSettings.load().lock_minute
    if minute and event.elapsed >= minute:
        event.live_locked_at = now or timezone.now()
        return ['live_locked_at']
    return []


def hold(event: Event, reason: str, *, by: str = 'system', now=None, save: bool = True) -> list[str]:
    """Suspend in-play trading on a match until staff reopen it. Keeps the
    first reason if it is already held. Returns the fields changed."""
    if event.live_hold_reason:
        return []
    event.live_hold_reason = f'{reason}'[:200]
    event.live_hold_at = now or timezone.now()
    fields = ['live_hold_reason', 'live_hold_at']
    if save:
        event.save(update_fields=fields)  # post_save publishes the suspension
    from apps.accounts import services as accounts_services
    accounts_services.audit(None, 'live_market_held', None, event_id=event.id, reason=event.live_hold_reason, by=by)
    if by == 'system':
        _flag_recent_bettors(event, reason)
    return fields


def release(event: Event, *, by: str) -> Event:
    """Staff reopen a held match. The lock minute can't be undone."""
    if not event.live_hold_reason:
        return event
    from apps.accounts import services as accounts_services
    accounts_services.audit(None, 'live_market_released', None, event_id=event.id,
                            reason=event.live_hold_reason, by=by)
    event.live_hold_reason, event.live_hold_at = '', None
    event.save(update_fields=['live_hold_reason', 'live_hold_at'])
    return event


def check_feed(event: Event, *, old_score, old_elapsed, now=None) -> list[str]:
    """Hold on data that can't be right: the score going down (a goal ruled out
    is a reason to stop too) or the clock running backwards. Only when the
    operator switched it on (hold_on_bad_feed)."""
    cfg = LiveTradingSettings.load()
    if cfg.keep_markets_open or not cfg.hold_on_bad_feed:
        return []
    new_score = (event.score_home, event.score_away)
    if None not in (*old_score, *new_score) and sum(new_score) < sum(old_score):
        return hold(event, f'Score went from {old_score[0]}-{old_score[1]} to {new_score[0]}-{new_score[1]}',
                    now=now, save=False)
    if old_elapsed is not None and event.elapsed is not None and event.elapsed < old_elapsed - CLOCK_SLACK:
        return hold(event, f'Match clock went back from {old_elapsed}\' to {event.elapsed}\'', now=now, save=False)
    return []


def check_price_jump(event: Event, old_prices, new_prices, *, now=None) -> list[str]:
    """Hold when a match-result price moves at least price_jump_percent in one
    update with no goal to explain it."""
    now = now or timezone.now()
    if event.last_goal_at and now - event.last_goal_at < GOAL_GRACE:
        return []
    cfg = LiveTradingSettings.load()
    limit = Decimal(cfg.price_jump_percent)
    if cfg.keep_markets_open or not limit:
        return []
    for label, old, new in zip(('home', 'draw', 'away'), old_prices, new_prices):
        if not old or not new:
            continue
        move = abs(Decimal(new) - Decimal(old)) / Decimal(old) * 100
        if move >= limit:
            return hold(event, f'{label.title()} price jumped {old} → {new} ({move:.0f}%) with no goal',
                        now=now, save=False)
    return []


def check_stake_burst(event_id: Optional[int], *, selection: str = '', outcome_id: Optional[int] = None,
                      now=None) -> None:
    """After an in-play bet: hold the match if more than burst_amount has been
    staked in play on this selection within burst_minutes."""
    if event_id is None:
        return
    cfg = LiveTradingSettings.load()
    if cfg.keep_markets_open or not cfg.burst_amount:
        return
    now = now or timezone.now()
    since = now - timedelta(minutes=cfg.burst_minutes)
    live = (Bet.Status.ACCEPTING, Bet.Status.OPEN)
    pick = Q(outcome_ref_id=outcome_id) if outcome_id else Q(event_ref_id=event_id, selection=selection, outcome_ref=None)
    singles = Bet.objects.filter(pick, status__in=live, placed_at__gte=since).aggregate(t=Sum('stake'))['t'] or 0
    leg_pick = Q(outcome_ref_id=outcome_id) if outcome_id else Q(event_ref_id=event_id, selection=selection, outcome_ref=None)
    slips = (BetSlip.objects.filter(status__in=live, placed_at__gte=since,
                                    id__in=BetLeg.objects.filter(leg_pick).values('slip_id'))
             .aggregate(t=Sum('stake'))['t'] or 0)
    total = Decimal(singles) + Decimal(slips)
    if total > cfg.burst_amount:
        event = Event.objects.select_for_update().filter(pk=event_id).first()
        if event is not None:
            hold(event, f'${total:.2f} staked in play on one selection in {cfg.burst_minutes} minutes', now=now)


def _flag_recent_bettors(event: Event, reason: str) -> None:
    """Players who bet in play on this match just before the guard stopped it
    get a low fraud signal; repeated across matches, it adds up."""
    from apps.risk import services as risk
    since = (event.live_hold_at or timezone.now()) - timedelta(minutes=LiveTradingSettings.load().burst_minutes)
    players = set(Bet.objects.filter(event_ref=event, placed_at__gte=since, status__in=(
        Bet.Status.ACCEPTING, Bet.Status.OPEN)).exclude(player_id=None).values_list('player_id', flat=True))
    players |= set(BetSlip.objects.filter(legs__event_ref=event, placed_at__gte=since, status__in=(
        BetSlip.Status.ACCEPTING, BetSlip.Status.OPEN)).exclude(player_id=None).values_list('player_id', flat=True))
    for pid in players:
        risk.safely(risk.flag, pid, 'live_bet_before_suspension', risk.Severity.LOW,
                    f'Bet in play on {event.name} just before it was suspended ({reason}).',
                    dedupe=f'event:{event.id}', data={'event_id': event.id, 'reason': reason})


# -- outcomes play has already decided -----------------------------------------

# Markets that stay open to the lock minute can still never offer a price on
# something already settled by the score or the clock: that is not a market
# that "might still happen", it is free money. Only outcomes that can no longer
# change are shut — everything undecided stays open.

def _goals(event: Event) -> Optional[tuple[int, int]]:
    if event.score_home is None or event.score_away is None:
        return None
    return event.score_home, event.score_away


def _line_decided(total: int, line, key: str) -> bool:
    return line is not None and key in ('over', 'under') and total > line


def outcome_decided(event: Event, market, outcome) -> bool:
    """Whether the match so far has already decided this outcome (won or lost
    for certain, whatever happens next). Conservative: only the cases that can
    only move one way — goals can't be un-scored — and a half that is over."""
    from .services import IN_PLAY_STATUSES
    if event.status not in IN_PLAY_STATUSES:
        return False
    period = market.period or 'ft'
    first_half_over = event.status in ('HT', '2H') or (event.elapsed or 0) > 45
    if period == '1h':
        return first_half_over
    if period != 'ft' or (market.metric or 'goals') != 'goals':
        return False
    score = _goals(event)
    if score is None:
        return False
    home, away = score
    total, kind, key = home + away, market.kind, outcome.key
    if kind == 'over_under':
        return _line_decided(total, market.line, key)
    if kind == 'home_over_under':
        return _line_decided(home, market.line, key)
    if kind == 'away_over_under':
        return _line_decided(away, market.line, key)
    if kind == 'btts':
        return home > 0 and away > 0
    if kind == 'team_to_score_home':
        return home > 0
    if kind == 'team_to_score_away':
        return away > 0
    if kind == 'clean_sheet_home':
        return away > 0
    if kind == 'clean_sheet_away':
        return home > 0
    if kind == 'correct_score':
        try:
            want_home, want_away = (int(p) for p in key.split(':'))
        except ValueError:
            return False
        return home > want_home or away > want_away
    if kind in ('exact_goals', 'home_exact_goals', 'away_exact_goals'):
        n = {'exact_goals': total, 'home_exact_goals': home, 'away_exact_goals': away}[kind]
        try:
            return n >= int(key[:-1]) if key.endswith('+') else n > int(key)
        except ValueError:
            return False
    return False


def close_decided(event: Event) -> int:
    """Shut the open outcomes play has decided, so boards show them closed (new
    bets on them are refused regardless — see services). Returns how many."""
    from .models import MarketOutcome
    closed = 0
    outcomes = MarketOutcome.objects.filter(
        market__event=event, market__settled=False, is_open=True, result=MarketOutcome.Result.PENDING,
    ).select_related('market')
    for outcome in outcomes:
        if outcome_decided(event, outcome.market, outcome):
            outcome.is_open = False
            outcome.save(update_fields=['is_open'])
            closed += 1
    return closed
