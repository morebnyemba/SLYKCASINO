"""Booking codes: save a bet slip's picks under a short code anyone can load.

A code stores picks only. Loading it re-reads every pick's current price and
whether it can still be backed, so a code shared yesterday never places a bet
at yesterday's price: finished or suspended picks come back unavailable.
"""
from __future__ import annotations

import secrets
from typing import Optional

from django.db import IntegrityError, transaction
from django.db.models import F

from .models import BookingCode, Event, MarketOutcome, Selection
from .services import _main_price, _started, in_play_bettable, trading_state

# No 0/O or 1/I/L, so a code read out loud or typed from a screenshot is unambiguous.
CODE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
CODE_LENGTH = 6
MAX_PICKS = 40


def _new_code() -> str:
    return ''.join(secrets.choice(CODE_ALPHABET) for _ in range(CODE_LENGTH))


def _normalise(selections) -> list[dict]:
    """Keep well-formed picks only: {'outcome_id'} or {'event_id', 'selection'}.
    Duplicates are dropped, and picks must point at existing rows."""
    if not isinstance(selections, list):
        raise ValueError('selections must be a list')
    picks: list[dict] = []
    seen: set[str] = set()
    for raw in selections:
        if not isinstance(raw, dict):
            continue
        if raw.get('outcome_id') is not None:
            try:
                pick = {'outcome_id': int(raw['outcome_id'])}
            except (TypeError, ValueError):
                continue
            key = f'o:{pick["outcome_id"]}'
        else:
            try:
                event_id = int(raw.get('event_id'))
            except (TypeError, ValueError):
                continue
            selection = raw.get('selection')
            if selection not in Selection.values:
                continue
            pick = {'event_id': event_id, 'selection': selection}
            key = f'e:{event_id}:{selection}'
        if key not in seen:
            seen.add(key)
            picks.append(pick)
    if not picks:
        raise ValueError('add at least one selection to book a code')
    if len(picks) > MAX_PICKS:
        raise ValueError(f'a booking code can hold at most {MAX_PICKS} selections')

    outcome_ids = {p['outcome_id'] for p in picks if 'outcome_id' in p}
    event_ids = {p['event_id'] for p in picks if 'event_id' in p}
    known_outcomes = set(MarketOutcome.objects.filter(pk__in=outcome_ids).values_list('pk', flat=True))
    known_events = set(Event.objects.filter(pk__in=event_ids).values_list('pk', flat=True))
    picks = [
        p for p in picks
        if (p.get('outcome_id') in known_outcomes) or (p.get('event_id') in known_events)
    ]
    if not picks:
        raise ValueError('none of these selections are available')
    return picks


def create_booking(selections, *, player_id: Optional[int] = None) -> BookingCode:
    picks = _normalise(selections)
    for _ in range(8):
        try:
            with transaction.atomic():
                return BookingCode.objects.create(code=_new_code(), selections=picks, player_id=player_id)
        except IntegrityError:
            continue  # code collision: draw another
    raise RuntimeError('could not allocate a booking code')


def _resolve(picks: list[dict]) -> list[dict]:
    """Each pick as a bet-slip leg with its current price and availability."""
    outcome_ids = [p['outcome_id'] for p in picks if 'outcome_id' in p]
    event_ids = [p['event_id'] for p in picks if 'event_id' in p]
    outcomes = {
        o.id: o for o in MarketOutcome.objects.filter(pk__in=outcome_ids).select_related('market__event')
    }
    events = {e.id: e for e in Event.objects.filter(pk__in=event_ids)}

    legs = []
    for p in picks:
        if 'outcome_id' in p:
            o = outcomes.get(p['outcome_id'])
            if o is None:
                continue
            event = o.market.event
            event_ok = in_play_bettable(event) if _started(event) else event.is_open
            available = bool(
                event_ok and o.market.is_open and not o.market.settled
                and o.is_open and o.result == MarketOutcome.Result.PENDING
            )
            legs.append({
                'event_id': event.id, 'event_name': event.name, 'selection': Selection.HOME,
                'outcome_id': o.id, 'market_id': o.market_id, 'market_name': o.market.name,
                'outcome_label': o.label, 'odds': str(o.odds), 'available': available,
                'starts_at': event.starts_at,
            })
        else:
            event = events.get(p['event_id'])
            if event is None:
                continue
            price = _main_price(event, p['selection'])
            legs.append({
                'event_id': event.id, 'event_name': event.name, 'selection': p['selection'],
                'outcome_id': None, 'market_id': None, 'market_name': None, 'outcome_label': None,
                'odds': str(price) if price is not None else None,
                'available': bool(price is not None and trading_state(event)['main_open']),
                'starts_at': event.starts_at,
            })
    return legs


def booking_payload(booking: BookingCode) -> dict:
    legs = _resolve(booking.selections)
    return {
        'code': booking.code,
        'created_at': booking.created_at,
        'legs': legs,
        'available': sum(1 for leg in legs if leg['available']),
    }


def load_booking(code: str) -> Optional[dict]:
    """Look a code up (case-insensitive, spaces ignored) and count the load."""
    code = ''.join((code or '').split()).upper()
    booking = BookingCode.objects.filter(code=code).first()
    if booking is None:
        return None
    BookingCode.objects.filter(pk=booking.pk).update(loads=F('loads') + 1)
    return booking_payload(booking)
