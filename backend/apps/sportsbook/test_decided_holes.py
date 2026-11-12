"""Placement can never be talked into a price or a pick that isn't on offer:
no invented prices, no bets on nothing, and in play only prices the live feed is
quoting right now (never a pre-match price, never one the feed has dropped)."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal as D

import pytest
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services as accounts
from apps.sportsbook import live_guard
from apps.sportsbook import services as sb
from apps.sportsbook.models import Bet, Event, LiveTradingSettings, Market, MarketOutcome
from apps.sportsbook.test_in_play import FEED_ODDS, LIVE, InPlayBase
from apps.wallet import services as wallet

pytestmark = pytest.mark.strict_bets


@LIVE
class LivePricesOnlyInPlay(InPlayBase):
    def setUp(self):
        super().setUp()
        LiveTradingSettings.objects.update_or_create(pk=1, defaults={'keep_markets_open': True})
        # A pre-match handicap the live feed never prices: home +1.5 at 1.30.
        m = Market.objects.create(event=self.event, key='asian_handicap:ft:1.5', name='Asian handicap',
                                  kind='asian_handicap', line=D('1.5'))
        self.handicap = MarketOutcome.objects.create(market=m, key='home', label='Home +1.5', odds=D('1.30'))

    def back(self, outcome, odds=None):
        return sb.place_bet(wallet='deposit', event='x', stake=D('5'), odds=odds or outcome.odds,
                            player_id=self.player.id, outcome_id=outcome.id)

    def test_a_pre_match_price_cannot_be_taken_in_play(self):
        self.feed(at=self.t0, goals=(3, 0))                       # 3-0 up: +1.5 is as good as won
        self.handicap.refresh_from_db()
        self.assertFalse(self.handicap.is_open)                   # closed on the board
        MarketOutcome.objects.filter(pk=self.handicap.pk).update(is_open=True)   # a stale board / direct request
        with self.assertRaises(sb.SelectionUnavailable):
            self.back(self.handicap)
        self.assertEqual(Bet.objects.count(), 0)

    def test_a_price_the_feed_stops_quoting_closes_after_the_grace_period(self):
        self.feed(at=self.t0)
        btts = MarketOutcome.objects.get(market__event=self.event, market__key='btts:ft', key='yes')
        no_btts = [b for b in FEED_ODDS if b['name'] != 'Both Teams to Score']
        self.feed(at=self.t0 + timedelta(seconds=30), odds=no_btts)
        btts.refresh_from_db()
        self.assertTrue(btts.is_open)                             # inside the 60s grace
        self.feed(at=self.t0 + timedelta(seconds=70), odds=no_btts)
        btts.refresh_from_db()
        self.assertFalse(btts.is_open)
        self.feed(at=self.t0 + timedelta(seconds=80))             # quoted again: back on offer
        btts.refresh_from_db()
        self.assertTrue(btts.is_open)

    def test_a_whole_match_pause_does_not_age_prices(self):
        self.feed(at=self.t0)
        self.feed(at=self.t0 + timedelta(seconds=300), blocked=True)
        self.event.refresh_from_db()
        self.assertTrue(live_guard.live_price_fresh(self.event, self.over_2_5().live_priced_at))
        self.assertTrue(self.over_2_5().is_open)

    def test_a_bet_confirms_only_when_the_feed_quotes_that_pick_again(self):
        self.feed(at=self.t0)
        btts = MarketOutcome.objects.get(market__event=self.event, market__key='btts:ft', key='yes')
        bet = self.back(btts)
        no_btts = [b for b in FEED_ODDS if b['name'] != 'Both Teams to Score']
        later = bet.placed_at + timedelta(seconds=8)
        self.feed(at=later, odds=no_btts)                         # the match updates, this pick isn't quoted
        self.assertEqual(sb.confirm_live_bet('bet', bet.id, now=later), 'accepting')
        end = bet.placed_at + timedelta(seconds=40)
        self.feed(at=end, odds=no_btts)
        self.assertEqual(sb.confirm_live_bet('bet', bet.id, now=end), 'rejected')        # never confirmed: refunded
        self.assertEqual(wallet.get_balances(self.player.id)['deposit'], D('100.00'))
        bet2 = self.back(self.over_2_5())
        self.feed(at=bet2.placed_at + timedelta(seconds=8))       # quoted again at the same price
        self.assertEqual(sb.confirm_live_bet('bet', bet2.id, now=bet2.placed_at + timedelta(seconds=8)), 'open')

    def test_the_live_match_result_needs_a_live_quote_too(self):
        self.feed(at=self.t0)
        without_1x2 = [b for b in FEED_ODDS if b['name'] != 'Fulltime Result']
        self.feed(at=self.t0 + timedelta(seconds=70), odds=without_1x2, home=None)
        self.event.refresh_from_db()
        self.assertFalse(sb.trading_state(self.event, now=self.t0 + timedelta(seconds=70))['main_open'])
        with self.assertRaises(sb.SelectionUnavailable):
            sb.place_bet(wallet='deposit', event='Arsenal', stake=D('5'), odds=self.event.odds, player_id=self.player.id,
                         event_id=self.event.id, selection='home')

    def test_admin_sets_the_grace_period(self):
        from django.contrib.auth.models import User
        staff = APIClient()
        staff.force_authenticate(User.objects.create_superuser('ops', 'o@example.com', 'x'))
        url = '/api/admin/sportsbook/live-trading/'
        self.assertEqual(staff.get(url).json()['live_price_grace_seconds'], 60)
        self.assertEqual(staff.put(url, {'live_price_grace_seconds': 120}, format='json').json()['live_price_grace_seconds'], 120)
        self.assertEqual(staff.put(url, {'live_price_grace_seconds': 5}, format='json').status_code, 400)


class NoInventedPricesOrPicks(TestCase):
    def setUp(self):
        self.player = accounts.register_player(username='chancer', email='ch@example.com', password='Chancer-pass-123', currency='USD')
        wallet.credit(player_id=self.player.id, amount=D('100'), kind='deposit', idempotency_key='c:d')
        soon = timezone.now() + timedelta(hours=3)
        self.event = Event.objects.create(name='A v B', odds=D('1.50'), odds_draw=D('4.00'), odds_away=D('6.00'), starts_at=soon)
        self.other = Event.objects.create(name='C v D', odds=D('2.00'), odds_draw=D('3.00'), odds_away=D('3.50'), starts_at=soon)
        self.api = APIClient()
        self.api.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(self.player.user).access_token}')

    def home(self, odds):
        return sb.place_bet(wallet='deposit', event='A v B', stake=D('10'), odds=D(odds), player_id=self.player.id,
                            event_id=self.event.id, selection='home')

    def test_pre_match_bets_are_struck_at_the_market_price_only(self):
        with self.assertRaises(sb.OddsChanged) as caught:
            self.home('50.00')
        self.assertEqual(caught.exception.current, D('1.50'))
        self.assertEqual(self.home('1.50').odds, D('1.50'))
        self.assertEqual(sb.place_bet(wallet='deposit', event='A v B', stake=D('10'), odds=D('4.00'), player_id=self.player.id,
                                      event_id=self.event.id, selection='draw').odds, D('4.00'))

    def test_the_api_reports_the_real_price(self):
        res = self.api.post('/api/bets/', {'event': 'A v B', 'event_id': self.event.id, 'selection': 'home', 'stake': '10',
                                           'odds': '50', 'wallet': 'deposit'}, format='json')
        self.assertEqual((res.status_code, res.json()['code'], res.json()['odds']), (409, 'odds_changed', '1.50'))
        self.assertEqual(Bet.objects.count(), 0)

    def test_a_selection_with_no_price_cannot_be_backed(self):
        Event.objects.filter(pk=self.event.pk).update(odds_draw=None)
        with self.assertRaises(sb.SelectionUnavailable):
            sb.place_bet(wallet='deposit', event='A v B', stake=D('10'), odds=D('4.00'), player_id=self.player.id,
                         event_id=self.event.id, selection='draw')

    def test_a_bet_must_be_on_a_real_match_or_market(self):
        with self.assertRaises(sb.SelectionUnavailable):
            sb.place_bet(wallet='deposit', event='Made up FC to win', stake=D('10'), odds=D('900'), player_id=self.player.id)
        with self.assertRaises(sb.SelectionUnavailable):
            sb.place_bet(wallet='deposit', event='ghost', stake=D('10'), odds=D('900'), player_id=self.player.id, event_id=987654)
        res = self.api.post('/api/bets/', {'event': 'Made up', 'stake': '10', 'odds': '900', 'wallet': 'deposit'}, format='json')
        self.assertEqual(res.status_code, 409)
        self.assertEqual(wallet.get_balances(self.player.id)['deposit'], D('100.00'))

    def test_every_leg_of_a_multiple_is_checked(self):
        real = {'event': 'A v B', 'odds': D('1.50'), 'event_id': self.event.id, 'selection': 'home'}
        for bad in ({'event': 'ghost', 'odds': D('40')},                                             # nothing behind it
                    {'event': 'C v D', 'odds': D('40'), 'event_id': self.other.id, 'selection': 'home'}):  # invented price
            with self.assertRaises((sb.SelectionUnavailable, sb.OddsChanged)):
                sb.place_accumulator(stake=D('10'), player_id=self.player.id, wallet='deposit', legs=[real, bad])
        slip = sb.place_accumulator(stake=D('10'), player_id=self.player.id, wallet='deposit', legs=[
            real, {'event': 'C v D', 'odds': D('2.00'), 'event_id': self.other.id, 'selection': 'home'}])
        self.assertEqual(slip.combined_odds, D('3.00'))
