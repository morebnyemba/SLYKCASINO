"""Cash-out house protection: every rule leans towards the house."""
from datetime import timedelta
from decimal import Decimal as D
from unittest.mock import patch

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.sportsbook import cashout
from apps.sportsbook import services as sb
from apps.sportsbook.models import Bet, CashoutSettings, Event, LiveTradingSettings
from apps.sportsbook.test_cashout import _event, _player
from apps.sportsbook.test_in_play import LIVE, InPlayBase


def _age(bet, seconds=120):
    Bet.objects.filter(pk=bet.pk).update(placed_at=timezone.now() - timedelta(seconds=seconds))
    bet.refresh_from_db()
    return bet


@pytest.mark.cashout_rules
class PreMatchRulesTests(TestCase):
    def setUp(self):
        self.player, _ = _player('house')
        self.ev = _event('Dynamos vs CAPS United')
        self.bet = sb.place_bet(wallet='deposit', event=self.ev.name, stake=D('10'), odds=D('2.00'),
                                player_id=self.player.id, event_id=self.ev.id, selection='home')

    def test_nothing_until_the_ticket_is_a_minute_old(self):
        offer = cashout.bet_offer(self.bet)
        self.assertFalse(offer.available)
        self.assertIn('shortly after', offer.reason)
        self.assertTrue(cashout.bet_offer(_age(self.bet)).available)

    def test_offers_are_capped_at_a_share_of_the_win_and_an_amount(self):
        bet = _age(self.bet)
        Event.objects.filter(pk=self.ev.pk).update(odds=D('1.01'))     # fair 10 x 2 / 1.01 x 0.95 = 18.81
        bet.refresh_from_db()
        self.assertEqual(cashout.bet_offer(bet).value, D('18.00'))        # 90% of the $20 possible win
        CashoutSettings.objects.update(max_amount=D('5'))
        self.assertEqual(cashout.bet_offer(bet).value, D('5.00'))

    def test_flagged_players_and_switched_off_bet_types_get_nothing(self):
        bet = _age(self.bet)
        with patch('apps.risk.services.needs_review', return_value=True):
            self.assertIn('account', cashout.bet_offer(bet).reason)
        CashoutSettings.objects.update(allow_singles=False)
        self.assertIn('single', cashout.bet_offer(bet).reason)


@pytest.mark.cashout_rules
@LIVE
class LiveRulesTests(InPlayBase):
    def setUp(self):
        super().setUp()
        LiveTradingSettings.objects.filter(pk=1).update(keep_markets_open=True)
        CashoutSettings.objects.update_or_create(pk=1, defaults={'live_delay_seconds': 3})
        self.feed()
        o = self.over_2_5()
        self.bet = Bet.objects.create(player_id=self.player.id, event='x', event_ref=self.event, outcome_ref=o,
                                      selection='home', stake=D('10'), odds=o.odds, wallet='deposit', status=Bet.Status.OPEN,
                                      in_play=True)
        _age(self.bet)

    def test_live_offers_use_the_bigger_in_play_margin(self):
        offer = cashout.bet_offer(self.bet)
        self.assertTrue(offer.available, offer.reason)
        self.assertEqual(offer.value, D('9.20'))                          # same price, 8% in-play margin

    def test_no_live_cash_out_late_or_while_the_feed_pauses(self):
        Event.objects.filter(pk=self.event.pk).update(elapsed=86)
        self.bet.refresh_from_db()
        self.assertFalse(cashout.bet_offer(self.bet).available)
        Event.objects.filter(pk=self.event.pk).update(elapsed=60, live_feed_paused=True)
        self.bet.refresh_from_db()
        self.assertFalse(cashout.bet_offer(self.bet).available)

    def test_a_goal_during_the_live_check_cancels_the_cash_out(self):
        value = cashout.bet_offer(self.bet).value
        goal = lambda _s: Event.objects.filter(pk=self.event.pk).update(last_goal_at=timezone.now())  # noqa: E731
        with patch('time.sleep', side_effect=goal) as slept:
            with self.assertRaisesMessage(cashout.CashoutUnavailable, 'A goal went in'):
                cashout.cash_out(kind='bet', ticket_id=self.bet.id, player_id=self.player.id, expected=value)
        slept.assert_called_once_with(3)
        self.bet.refresh_from_db()
        self.assertEqual(self.bet.status, Bet.Status.OPEN)

    def test_a_quiet_live_check_pays(self):
        value = cashout.bet_offer(self.bet).value
        with patch('time.sleep'):
            ticket, record = cashout.cash_out(kind='bet', ticket_id=self.bet.id, player_id=self.player.id, expected=value)
        self.assertEqual((ticket.status, record.amount), (Bet.Status.CASHED_OUT, value))
