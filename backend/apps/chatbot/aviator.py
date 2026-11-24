"""Aviator played entirely from WhatsApp: no website, no live data stream.

A WhatsApp message takes a second or more each way, so nobody can watch the plane from chat.
The game is played the way it is fair over a slow link:

* Every chat bet has an **auto cash-out** (e.g. 2.00x), decided by the server clock exactly
  like the website's (jet.services). Players can still send *CASH* while it flies: the server
  pays the multiplier at the moment the message arrives.
* A bet confirmed in chat is an **AviatorOrder**. If the current round is still taking bets it
  goes straight in, otherwise the jet runner puts it into the next round as betting opens
  (on_open), so a slow message never misses a round. Autoplay repeats it for up to MAX_ROUNDS.
* After each crash the player gets the result (on_crash): where it flew away, won or lost,
  and their balance. When it takes off they're told they can send *CASH* (on_flight).

Limits are the chat's own (most per ticket, daily chat limit, PIN above the threshold) plus
the game's (min/max bet, round limit) and responsible gambling, checked for every round.
"""
from __future__ import annotations

import logging
import threading
from datetime import timedelta
from decimal import Decimal, InvalidOperation
from typing import Optional

from django.db import transaction
from django.utils import timezone

from . import services
from .models import AviatorOrder, AviatorPlay, ChatbotSettings, ChatLink, ChatTicket

logger = logging.getLogger(__name__)

MAX_ROUNDS = 20
JOIN_MARGIN = timedelta(seconds=1.5)       # less than this left on the countdown: wait for the next round
STAKES = ('0.50', '1', '2', '5', '10')
TARGETS = ('1.50', '2', '3', '5', '10')


def _money(v) -> str:
    return f'${Decimal(v):.2f}'


def _x(v) -> str:
    return f'{Decimal(v):.2f}x'


def parse_amount(text: str) -> Optional[Decimal]:
    try:
        v = Decimal(text.strip().lstrip('$').rstrip('xX')).quantize(Decimal('0.01'))
    except (InvalidOperation, ValueError):
        return None
    return v if v > 0 else None


def _send(channel: str, address: str, replies: list[dict]) -> None:
    """Send from the jet runner without holding up the round."""
    def run():
        try:
            services.send_now(channel, address, replies)
        except Exception:  # noqa: BLE001
            logger.exception('aviator message to …%s failed', address[-4:])
        finally:
            if threading.current_thread() is not threading.main_thread():
                from django.db import connection
                connection.close()
    transaction.on_commit(lambda: threading.Thread(target=run, daemon=True).start())


def _balance(player_id: int) -> Decimal:
    from apps.wallet import services as wallet
    b = wallet.get_balances(player_id)
    return Decimal(b['deposit']) + Decimal(b['winnings'])


def free_spins(player_id: int, now=None) -> int:
    from apps.jet.models import JetFreeBet
    now = now or timezone.now()
    return JetFreeBet.objects.filter(player_id=player_id, status=JetFreeBet.Status.AVAILABLE, expires_at__gt=now).count()


# -- placing ------------------------------------------------------------------------------------
class StopOrder(Exception):
    """The order can't go on (balance, limits, game paused...): the message says why."""


def place(order: AviatorOrder, rnd, *, now=None):
    """Put one round of the order into `rnd` (taking bets). Returns the jet bet; raises StopOrder."""
    from apps.accounts.models import Player
    from apps.jet import services as jet
    from apps.jet.models import JetFreeBet
    from apps.wallet.services import InsufficientFunds
    now = now or timezone.now()
    if not ChatbotSettings.load().allow_aviator:
        raise StopOrder('Aviator on WhatsApp is paused right now.')
    player = Player.objects.filter(pk=order.player_id).first()
    link = ChatLink.objects.filter(channel=order.channel, address=order.address, player_id=order.player_id).first()
    if player is None or link is None:
        raise StopOrder('This number is no longer linked to the account.')
    free_id = None
    if order.free:
        free = (JetFreeBet.objects.filter(player_id=player.id, status=JetFreeBet.Status.AVAILABLE, expires_at__gt=now)
                .order_by('expires_at').first())
        if free is None:
            raise StopOrder('No free spins left.')
        free_id = free.pk
    else:
        try:
            services.check_stake(link, order.stake)
        except services.ChatError as exc:
            raise StopOrder(str(exc))
    last = None
    for slot in (1, 2):              # the player may also be playing slot 1 on the website
        try:
            with transaction.atomic():
                bet = jet.place_bet(player=player, stake=None if order.free else order.stake, slot=slot,
                                    auto_cashout=order.auto_cashout, free_bet_id=free_id, now=now)
                AviatorPlay.objects.create(order=order, bet_id=bet.id, round_id=rnd.id)
                if not order.free:
                    ChatTicket.objects.create(channel=order.channel, player_id=order.player_id, kind=ChatTicket.Kind.JET,
                                              object_id=bet.id, stake=bet.stake)
                order.placed += 1
                order.staked += Decimal('0') if order.free else bet.stake
                order.save(update_fields=['placed', 'staked', 'updated_at'])
            return bet
        except jet.JetError as exc:
            last = str(exc)
            if 'slot' in last:
                continue
            if 'closed' in last or 'full' in last:
                return None             # try the next round
            raise StopOrder(last)
        except InsufficientFunds as exc:
            raise StopOrder(str(exc) or 'Not enough balance.')
    raise StopOrder(last or 'You already have two bets in this round.')


def _stop(order: AviatorOrder, why: str) -> None:
    order.status, order.note = AviatorOrder.Status.STOPPED, why[:200]
    order.save(update_fields=['status', 'note', 'updated_at'])
    done = f' after {order.placed} round{"" if order.placed == 1 else "s"}' if order.placed else ''
    _send(order.channel, order.address, [{'text': f'✈️ *Aviator stopped*{done}: {why}', 'buttons': [
        ['DEPOSIT', '💳 Deposit'], ['AVIATOR', '✈️ Aviator'], ['MENU', '🏠 Menu']]}])


def start(order: AviatorOrder, *, now=None) -> Optional[object]:
    """A just-confirmed order: straight into the current round when it's still taking bets."""
    from apps.jet.models import JetRound
    now = now or timezone.now()
    rnd = JetRound.objects.filter(status=JetRound.Status.BETTING).order_by('-id').first()
    if rnd is None or rnd.betting_ends_at - now < JOIN_MARGIN:
        return None
    return place(order, rnd, now=now)


def on_open(rnd) -> None:
    """Betting just opened: every active chat order that isn't already riding joins this round."""
    riding = set(AviatorPlay.objects.filter(reported=False).values_list('order_id', flat=True))
    for order in AviatorOrder.objects.filter(status=AviatorOrder.Status.ACTIVE):
        if order.placed >= order.rounds or order.pk in riding:
            continue
        try:
            place(order, rnd)
        except StopOrder as exc:
            _stop(order, str(exc))
        except Exception:  # noqa: BLE001
            logger.exception('aviator order %s failed to place', order.pk)


def on_flight(rnd) -> None:
    """Take-off: tell players on their first round that they can cash out by hand."""
    from apps.jet.models import JetBet
    plays = AviatorPlay.objects.filter(round_id=rnd.id, reported=False).select_related('order')
    bets = JetBet.objects.in_bulk([p.bet_id for p in plays])
    for p in plays:
        bet, order = bets.get(p.bet_id), p.order
        if bet is None or bet.status != JetBet.Status.ACTIVE or order.placed != 1:
            continue
        what = 'free spin' if bet.is_free else _money(bet.stake)
        _send(order.channel, order.address, [{
            'text': f'🛫 *Round {rnd.id} is flying!* Your {what} cashes out by itself at *{_x(order.auto_cashout)}*.\n'
                    'Send *CASH* to cash out now instead.',
            'buttons': [['CASH', '💰 CASH OUT']]}])


def on_crash(rnd) -> None:
    """The plane flew away: send every chat player their result."""
    from apps.jet.models import JetBet
    plays = list(AviatorPlay.objects.filter(round_id=rnd.id, reported=False).select_related('order'))
    bets = JetBet.objects.in_bulk([p.bet_id for p in plays])
    for p in plays:
        bet, order = bets.get(p.bet_id), p.order
        if bet is None:
            continue
        with transaction.atomic():
            order = AviatorOrder.objects.select_for_update().get(pk=order.pk)
            AviatorPlay.objects.filter(pk=p.pk).update(reported=True)
            won = bet.payout if bet.status == JetBet.Status.CASHED else Decimal('0')
            order.settled += 1
            order.won += won
            finished = order.settled >= order.rounds or (order.status != AviatorOrder.Status.ACTIVE and order.settled >= order.placed)
            if finished and order.status == AviatorOrder.Status.ACTIVE:
                order.status = AviatorOrder.Status.DONE
            order.save(update_fields=['settled', 'won', 'status', 'updated_at'])
        _send(order.channel, order.address, [_result(rnd, bet, order, finished)])


def _result(rnd, bet, order: AviatorOrder, finished: bool) -> dict:
    from apps.jet.models import JetBet
    what = 'free spin' if bet.is_free else _money(bet.stake)
    if bet.status == JetBet.Status.CASHED:
        gain = bet.payout if (bet.is_free or bet.wallet == 'bonus') else bet.payout - bet.stake
        head = (f'✅ *Cashed out at {_x(bet.cashout_multiplier)}!* Your {what} won *{_money(bet.payout)}*'
                + (' (paid as bonus)' if bet.is_free else f' (+{_money(gain)})') + '.')
    elif bet.status == JetBet.Status.REFUNDED:
        head = f'↩️ Your {what} was refunded.'
    else:
        head = f'💥 Flew away before {_x(order.auto_cashout)}: your {what} lost.'
    lines = [f'✈️ Round {rnd.id} flew away at *{_x(rnd.crash_point)}*', head]
    if order.rounds > 1:
        lines.append(f'Autoplay: round {order.settled} of {order.rounds}')
    if finished and order.rounds > 1:
        net = order.won - order.staked
        lines.append(f'🏁 *Autoplay done*: staked {_money(order.staked)}, won {_money(order.won)} '
                     f'({"+" if net >= 0 else "−"}{_money(abs(net))}).')
    lines.append(f'Balance: *{_money(_balance(order.player_id))}*')
    if finished or order.status != AviatorOrder.Status.ACTIVE:
        buttons = [['AV AGAIN', '🔁 Play again'], ['AVIATOR', '✈️ Aviator'], ['MENU', '🏠 Menu']]
    else:
        buttons = [['AV STOP', '⏹ Stop autoplay'], ['AVIATOR', '✈️ Aviator']]
    return {'text': '\n'.join(lines), 'buttons': buttons}


def cash_now(player_id: int, address: str, channel: str) -> list[str]:
    """CASH: cash out this number's riding bets at the multiplier the plane is at now."""
    from apps.jet import services as jet
    from apps.jet.models import JetBet, JetRound
    plays = AviatorPlay.objects.filter(reported=False, order__player_id=player_id, order__address=address,
                                       order__channel=channel)
    out = []
    for bet in JetBet.objects.filter(pk__in=[p.bet_id for p in plays], status=JetBet.Status.ACTIVE).select_related('round'):
        if bet.round.status == JetRound.Status.BETTING:
            out.append('⏳ The round hasn’t taken off yet: your bet is waiting. Send *AV STOP* to take it back.')
            continue
        try:
            paid = jet.cash_out(player_id=player_id, bet_id=bet.id)
            out.append(f'💰 *Cashed out at {_x(paid.cashout_multiplier)}!* You won *{_money(paid.payout)}*.')
        except jet.JetError as exc:
            out.append(f'💥 {exc}')
    return out


def stop(player_id: int, address: str, channel: str) -> tuple[int, int]:
    """AV STOP: end autoplay and take back a bet still waiting for take-off. (stopped, refunded)"""
    from apps.jet import services as jet
    from apps.jet.models import JetBet, JetRound
    orders = list(AviatorOrder.objects.filter(status=AviatorOrder.Status.ACTIVE, player_id=player_id, address=address,
                                              channel=channel))
    refunded = 0
    for play in AviatorPlay.objects.filter(order__in=orders, reported=False):
        bet = JetBet.objects.select_related('round').filter(pk=play.bet_id, status=JetBet.Status.ACTIVE).first()
        if bet and bet.round.status == JetRound.Status.BETTING:
            try:
                jet.cancel_bet(player_id=player_id, bet_id=bet.id)
                ChatTicket.objects.filter(kind=ChatTicket.Kind.JET, object_id=bet.id).delete()
                play.delete()
                AviatorOrder.objects.filter(pk=play.order_id).update(placed=max(0, play.order.placed - 1),
                                                                     staked=play.order.staked - bet.stake)
                refunded += 1
            except jet.JetError:
                pass
    for o in orders:
        o.refresh_from_db()
        o.status, o.note = AviatorOrder.Status.STOPPED, 'Stopped by the player'
        o.save(update_fields=['status', 'note', 'updated_at'])
    return len(orders), refunded
