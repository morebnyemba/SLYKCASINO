"""What bookmakers do in play: a bet stop on every goal (nothing can be taken at a pre-goal
price), and the player's choice for odds that move before a bet is struck."""
from datetime import timedelta
from decimal import Decimal as D

import pytest
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services as account_services
from apps.sportsbook import live_guard
from apps.sportsbook import services as sb
from apps.sportsbook.models import Event, LiveTradingSettings, MarketOutcome
from apps.sportsbook.test_in_play import LIVE, InPlayBase, _snapshot
from apps.wallet import services as wallet_services


@pytest.mark.betstop
@LIVE
class BetStopTests(InPlayBase):
    def setUp(self):
        super().setUp()
        LiveTradingSettings.objects.filter(pk=1).update(keep_markets_open=True, betstop_seconds=30)

    def refreshed(self):
        self.event.refresh_from_db()
        return self.event

    def bet_over(self):
        o = self.over_2_5()
        return sb.place_bet(event='x', stake=D('5'), odds=o.odds, player_id=self.player.id, event_id=self.event.id,
                            outcome_id=o.id, wallet='deposit')

    def test_a_goal_suspends_everything_until_new_prices_arrive(self):
        self.feed()
        self.assertIsNone(sb.outcome_unavailable(self.refreshed(), self.over_2_5().market, self.over_2_5()))
        self.feed(goals=(1, 0))                                           # goal: bet stop
        event = self.refreshed()
        self.assertFalse(sb.in_play_bettable(event))
        self.assertIn('Goal', live_guard.closed_reason(event))
        with self.assertRaises(sb.SelectionUnavailable):
            self.bet_over()
        # The pause is over, but the feed hasn't priced anything since the goal: still suspended.
        then = timezone.now() - timedelta(seconds=40)                     # the goal delivery, 40 seconds ago
        Event.objects.filter(pk=self.event.pk).update(last_goal_at=then, live_main_at=then, live_priced_at=then)
        MarketOutcome.objects.filter(market__event=self.event).update(live_priced_at=then)
        event = self.refreshed()
        self.assertTrue(sb.in_play_bettable(event))
        self.assertIsNotNone(sb.outcome_unavailable(event, self.over_2_5().market, self.over_2_5()))
        self.assertFalse(sb.trading_state(event)['main_open'])
        self.feed(goals=(1, 0))                                           # new prices after the goal
        event = self.refreshed()
        self.assertIsNone(sb.outcome_unavailable(event, self.over_2_5().market, self.over_2_5()))
        self.assertTrue(sb.trading_state(event)['main_open'])
        self.assertEqual(self.bet_over().stake, D('5.00'))

    def test_bet_stop_can_be_switched_off(self):
        LiveTradingSettings.objects.filter(pk=1).update(betstop_seconds=0)
        self.feed()
        self.feed(goals=(1, 0))
        self.assertTrue(sb.in_play_bettable(self.refreshed()))


class OddsChangePolicyTests(TestCase):
    """Accept higher odds (the default on the slip), accept any, or always ask."""

    def setUp(self):
        self.player = account_services.register_player(username='oddsman', email='o@example.com', password='Passw0rd!',
                                                       currency='USD')
        wallet_services.credit(player_id=self.player.id, amount=D('100'), kind='deposit', idempotency_key='odds:dep')
        self.event = Event.objects.create(name='Spurs vs Leeds', odds=D('2.00'), odds_draw=D('3.30'), odds_away=D('3.60'),
                                          is_open=True, has_odds=True, starts_at=timezone.now() + timedelta(hours=2))
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(self.player.user).access_token}')

    def bet(self, seen, policy):
        return self.client.post('/api/bets/', {'event': 'Spurs vs Leeds', 'event_id': self.event.id, 'selection': 'home',
                                               'stake': '5', 'odds': seen, 'wallet': 'deposit', 'accept_odds': policy},
                                format='json')

    def test_higher_odds_are_taken_lower_ones_asked(self):
        res = self.bet('1.90', 'higher')                                   # the price rose to 2.00
        self.assertEqual(res.status_code, 201)
        self.assertEqual(D(res.json()['odds']), D('2.00'))
        res = self.bet('2.10', 'higher')                                   # it fell: ask the player
        self.assertEqual((res.status_code, res.json()['code']), (409, 'odds_changed'))

    def test_any_takes_the_new_price_and_ask_never_does(self):
        self.assertEqual(self.bet('2.10', 'any').status_code, 201)
        self.assertEqual(self.bet('1.90', 'ask').status_code, 409)
