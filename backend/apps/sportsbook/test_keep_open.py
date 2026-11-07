"""The operator's rule: every market on every upcoming and live match stays open
until the lock minute (75'), then everything locks. Nothing suspends a market
by itself before then; only what play has already decided stays shut."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.sportsbook import live_guard
from apps.sportsbook import services as sb
from apps.sportsbook.clients import LiveOddsSnapshot
from apps.sportsbook.market_feed import parse_live_odds
from apps.sportsbook.models import Event, LiveTradingSettings, Market, MarketOutcome
from apps.sportsbook.test_in_play import FEED_ODDS, LIVE, InPlayBase, _v
from apps.sportsbook.test_live_guard import snap
from apps.sportsbook.unlock import unlock_markets

D = Decimal


def snapshot(odds=FEED_ODDS, *, elapsed=30, goals=(0, 0), home='1.50', status='Second Half', blocked=False,
             main_suspended=False):
    one_x_two, markets = parse_live_odds(odds, first_half=status == 'First Half')
    return LiveOddsSnapshot(
        external_id='555', status=status, elapsed=elapsed, goals_home=goals[0], goals_away=goals[1],
        blocked=blocked, main_suspended=main_suspended,
        one_x_two=None if main_suspended else (D(home), one_x_two[1], one_x_two[2]), markets=tuple(markets))


@LIVE
class KeepOpenTests(InPlayBase):
    def setUp(self):
        super().setUp()
        LiveTradingSettings.objects.update_or_create(pk=1, defaults={'keep_markets_open': True})
        self.now = self.t0

    def apply(self, seconds=0, **kw):
        return sb.apply_live_odds(snapshot(**kw), now=self.now + timedelta(seconds=seconds))

    def market(self, key):
        return Market.objects.get(event=self.event, key=key)

    def refreshed(self):
        self.event.refresh_from_db()
        return self.event

    def test_default_is_on_and_lock_is_75(self):
        LiveTradingSettings.objects.all().delete()
        cfg = LiveTradingSettings.load()
        self.assertTrue(cfg.keep_markets_open)
        self.assertEqual(cfg.lock_minute, 75)

    def test_markets_the_feed_stops_offering_stay_open_at_their_last_price(self):
        self.apply()
        without_btts = [b for b in FEED_ODDS if b['name'] != 'Both Teams to Score']
        self.apply(10, odds=without_btts)
        btts = self.market('btts:ft')
        self.assertTrue(btts.is_open)
        self.assertTrue(all(o.is_open for o in btts.outcomes.all()))
        self.assertEqual(sorted(o.odds for o in btts.outcomes.all()), [D('1.60'), D('2.20')])

    def test_a_market_the_feed_suspends_price_by_price_stays_open(self):
        self.apply()
        suspended = [{'id': 69, 'name': 'Both Teams to Score',
                      'values': [_v('Yes', '2.20', suspended=True), _v('No', '1.60', suspended=True)]}]
        self.apply(10, odds=[FEED_ODDS[0], *suspended])
        self.assertTrue(self.market('btts:ft').is_open)

    def test_a_feed_pause_of_any_length_keeps_the_match_open(self):
        self.apply()
        self.apply(600, blocked=True)           # ten minutes paused
        self.assertTrue(sb.in_play_bettable(self.refreshed(), now=self.now + timedelta(seconds=600)))
        self.assertTrue(self.refreshed().live_main_open)
        self.assertTrue(self.market('btts:ft').is_open)

    def test_a_paused_1x2_stays_open(self):
        self.apply()
        self.apply(10, main_suspended=True)
        self.assertTrue(self.refreshed().live_main_open)
        self.assertTrue(sb.in_play_bettable(self.event, now=self.now + timedelta(seconds=10)))

    def test_a_quiet_feed_does_not_suspend_but_bets_wait_for_a_fresh_price(self):
        self.apply()
        later = self.now + timedelta(minutes=10)
        self.assertTrue(sb.in_play_bettable(self.refreshed(), now=later))
        bet = sb.place_bet(wallet='deposit', event='Over 2.5', stake=D('10'), odds=D('1.80'), player_id=self.player.id,
                           outcome_id=self.over_2_5().id)
        self.assertEqual(bet.status, 'accepting')
        # No fresh price after the bet: refunded, never accepted blind.
        self.assertEqual(sb.confirm_live_bet('bet', bet.id, now=bet.placed_at + timedelta(seconds=120)), 'rejected')

    def test_a_poll_missing_the_match_locks_nothing(self):
        from unittest.mock import patch

        from apps.sportsbook.clients import ApiFootballClient
        self.apply()
        with patch.object(ApiFootballClient, 'fetch_live_odds', return_value=[]):
            sb.sync_live_odds(now=self.now + timedelta(minutes=30))
        self.assertTrue(sb.in_play_bettable(self.refreshed(), now=self.now + timedelta(minutes=5)))

    def test_automatic_holds_are_off_while_markets_are_kept_open(self):
        LiveTradingSettings.objects.update_or_create(pk=1, defaults={
            'price_jump_percent': 50, 'burst_amount': D('1'), 'hold_on_bad_feed': True})
        self.apply(0, home='1.50', elapsed=30)
        self.apply(10, home='5.00', elapsed=31)                      # a 230% jump, no goal
        self.apply(20, home='5.00', elapsed=10)                      # the clock goes back
        self.assertEqual(self.refreshed().live_hold_reason, '')
        sb.place_bet(wallet='deposit', event='Over 2.5', stake=D('50'), odds=D('1.80'), player_id=self.player.id,
                     outcome_id=self.over_2_5().id)                  # a burst of money
        self.assertEqual(self.refreshed().live_hold_reason, '')

    def test_staff_can_still_suspend_a_match_by_hand(self):
        self.apply()
        live_guard.hold(self.refreshed(), 'Red card not in the feed', by='staff')
        self.assertFalse(sb.in_play_bettable(self.refreshed(), now=self.now))

    def test_open_until_74_then_locked_at_75(self):
        self.apply(0, elapsed=74)
        self.assertTrue(sb.in_play_bettable(self.refreshed(), now=self.now))
        self.apply(5, elapsed=75)
        event = self.refreshed()
        self.assertIsNotNone(event.live_locked_at)
        self.assertFalse(sb.in_play_bettable(event, now=self.now))
        self.assertEqual(live_guard.closed_reason(event), "In-play betting closes at 75'")
        self.apply(10, elapsed=70)                                   # a clock glitch can't reopen it
        self.assertFalse(sb.in_play_bettable(self.refreshed(), now=self.now))

    def test_a_silent_feed_cannot_keep_a_match_open_past_the_lock(self):
        self.apply()
        event = self.refreshed()
        # starts_at is 60 minutes ago: lock minute + half-time and stoppage allowance is 93.
        self.assertTrue(sb.in_play_bettable(event, now=event.starts_at + timedelta(minutes=92)))
        self.assertFalse(sb.in_play_bettable(event, now=event.starts_at + timedelta(minutes=94)))
        self.assertEqual(live_guard.closed_reason(event, now=event.starts_at + timedelta(minutes=94)),
                         "In-play betting closes at 75'")
        self.assertEqual(sb.trading_state(event, now=event.starts_at + timedelta(minutes=94))['live_closed'],
                         "In-play betting closes at 75'")

    def test_outcomes_play_has_decided_close_but_undecided_ones_stay_open(self):
        self.apply(0, goals=(1, 0))
        self.assertTrue(self.market('btts:ft').is_open)
        self.assertTrue(all(o.is_open for o in self.market('over_under:ft:2.5').outcomes.all()))
        self.apply(10, goals=(2, 1))                                  # 3 goals, both sides scored
        self.assertFalse(any(o.is_open for o in self.market('over_under:ft:2.5').outcomes.all()))
        self.assertFalse(any(o.is_open for o in self.market('btts:ft').outcomes.all()))
        self.assertTrue(self.refreshed().live_main_open)              # the match result is still undecided
        with self.assertRaises(sb.SelectionUnavailable):
            sb.place_bet(wallet='deposit', event='Over 2.5', stake=D('5'), odds=D('1.80'), player_id=self.player.id,
                         outcome_id=self.over_2_5().id)

    def test_first_half_markets_close_when_the_half_is_over(self):
        self.apply(0, status='First Half', elapsed=30)
        self.assertTrue(self.market('match_result:1h').is_open)
        self.apply(10, status='Second Half', elapsed=50)
        self.assertFalse(any(o.is_open for o in self.market('match_result:1h').outcomes.all()))

    def test_decided_outcomes_pure_cases(self):
        def decided(kind, key, line, goals):
            self.event.score_home, self.event.score_away, self.event.status = *goals, '2H'
            market = Market(event=self.event, kind=kind, line=line, period='ft', metric='goals')
            return live_guard.outcome_decided(self.event, market, MarketOutcome(key=key))
        self.assertTrue(decided('over_under', 'over', D('1.5'), (1, 1)))
        self.assertTrue(decided('over_under', 'under', D('1.5'), (1, 1)))
        self.assertFalse(decided('over_under', 'over', D('2.5'), (1, 1)))
        self.assertFalse(decided('over_under', 'under', D('2'), (1, 1)))     # a push line isn't decided
        self.assertTrue(decided('correct_score', '0:0', None, (1, 0)))
        self.assertFalse(decided('correct_score', '2:1', None, (1, 0)))
        self.assertTrue(decided('exact_goals', '1', None, (1, 1)))
        self.assertTrue(decided('exact_goals', '2+', None, (1, 1)))
        self.assertFalse(decided('exact_goals', '3', None, (1, 1)))
        self.assertFalse(decided('match_result', 'home', None, (3, 0)))      # never decided mid-game
        self.assertFalse(decided('btts', 'yes', None, (3, 0)))


class UnlockTests(TestCase):
    def make(self, name, *, status='NS', starts=None, is_open=False, locked=False, hold=''):
        now = timezone.now()
        event = Event.objects.create(
            name=name, status=status, is_open=is_open, odds=D('2'), odds_draw=D('3'), odds_away=D('4'),
            starts_at=now + timedelta(hours=3) if starts is None else starts,
            live_locked_at=now if locked else None, live_hold_reason=hold, elapsed=60 if status in ('1H', '2H') else None)
        market = Market.objects.create(event=event, key='btts:ft', name='BTTS', kind='btts', is_open=False)
        MarketOutcome.objects.create(market=market, key='yes', label='Yes', odds=D('1.9'), is_open=False)
        MarketOutcome.objects.create(market=market, key='no', label='No', odds=D('1'), is_open=False)   # no real price
        return event

    def run_unlock(self):
        return unlock_markets(Event=Event, Market=Market, MarketOutcome=MarketOutcome, lock_minute=75)

    def state(self, event):
        event.refresh_from_db()
        market = event.markets.get()
        return event.is_open, market.is_open, sorted(o.is_open for o in market.outcomes.all())

    def test_reopens_upcoming_and_live_matches(self):
        upcoming = self.make('Upcoming')
        live = self.make('Live', status='2H', starts=timezone.now() - timedelta(minutes=70), hold='Suspended by staff')
        report = self.run_unlock()
        self.assertEqual(self.state(upcoming), (True, True, [False, True]))   # an outcome with no price stays shut
        self.assertEqual(self.state(live), (True, True, [False, True]))
        self.assertEqual(live.live_hold_reason, '')
        self.assertEqual((report['events'], report['holds_cleared']), (2, 1))

    def test_leaves_finished_voided_past_the_lock_and_settled_alone(self):
        finished = self.make('Done', status='FT', starts=timezone.now() - timedelta(hours=3))
        postponed = self.make('Postponed', status='PST')
        locked = self.make('Locked', status='2H', locked=True, starts=timezone.now() - timedelta(minutes=95))
        silent = self.make('Silent feed', status='2H', starts=timezone.now() - timedelta(minutes=100))
        settled = self.make('Settled market')
        Market.objects.filter(event=settled).update(settled=True)
        self.run_unlock()
        for event in (finished, postponed, locked, silent):
            self.assertEqual(self.state(event), (False, False, [False, False]), event.name)
        self.assertEqual(self.state(settled)[1:], (False, [False, False]))

    def test_admin_endpoint_unlocks_and_toggles_the_rule(self):
        event = self.make('Upcoming')
        staff = APIClient()
        staff.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))
        self.assertEqual(APIClient().post('/api/admin/sportsbook/unlock-markets/').status_code, 401)
        res = staff.post('/api/admin/sportsbook/unlock-markets/')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.state(event), (True, True, [False, True]))
        self.assertTrue(staff.get('/api/admin/sportsbook/live-trading/').json()['keep_markets_open'])
        res = staff.put('/api/admin/sportsbook/live-trading/', {'keep_markets_open': False}, format='json')
        self.assertFalse(res.json()['keep_markets_open'])


SHORT_ODDS = [
    FEED_ODDS[0],
    {'id': 69, 'name': 'Both Teams to Score', 'values': [_v('Yes', '1.02'), _v('No', '12.00')]},
    {'id': 12, 'name': 'Double Chance', 'values': [_v('Home/Draw', '1.05'), _v('Home/Away', '1.30'), _v('Draw/Away', '2.60')]},
]


@LIVE
class LiveFloorTests(InPlayBase):
    """Prices too short to take in play — a selection at 1.02 is as good as won."""

    def setUp(self):
        super().setUp()
        LiveTradingSettings.objects.update_or_create(pk=1, defaults={'keep_markets_open': True})

    def outcome(self, price):
        """The outcome priced `price` in the fixture feed above."""
        return MarketOutcome.objects.get(market__event=self.event, odds=D(price), market__kind__in=('btts', 'double_chance'))

    def bet(self, outcome, **kw):
        return sb.place_bet(wallet='deposit', event='Over', stake=D('5'), odds=outcome.odds, player_id=self.player.id,
                            outcome_id=outcome.id, **kw)

    def test_a_price_below_the_floor_is_refused_in_play_but_the_floor_itself_is_fine(self):
        self.feed(odds=SHORT_ODDS)
        with self.assertRaises(sb.SelectionUnavailable):                   # already closed on the board
            self.bet(self.outcome('1.02'))
        MarketOutcome.objects.filter(pk=self.outcome('1.02').pk).update(is_open=True)   # a stale board
        with self.assertRaisesMessage(sb.SelectionUnavailable, 'too short'):
            self.bet(self.outcome('1.02'))
        self.assertEqual(self.bet(self.outcome('1.05')).status, 'accepting')  # exactly the floor
        self.assertEqual(self.bet(self.outcome('1.30')).status, 'accepting')

    def test_boards_show_short_prices_closed(self):
        self.feed(odds=SHORT_ODDS)
        self.assertFalse(self.outcome('1.02').is_open)
        self.assertTrue(self.outcome('1.05').is_open)

    def test_a_short_live_leg_cannot_pad_a_multiple(self):
        self.feed(odds=SHORT_ODDS)
        short = self.outcome('1.02')
        MarketOutcome.objects.filter(pk=short.pk).update(is_open=True)
        legs = [{'event': 'A', 'odds': D('1.02'), 'outcome_id': short.id},
                {'event': 'B', 'odds': D('2.00'), 'event_id': None}]
        with self.assertRaisesMessage(sb.SelectionUnavailable, 'too short'):
            sb.place_accumulator(stake=D('5'), legs=legs, player_id=self.player.id, wallet='deposit')

    def test_the_match_result_obeys_the_floor_too(self):
        self.feed(home='1.03')
        with self.assertRaisesMessage(sb.SelectionUnavailable, 'too short'):
            sb.place_bet(wallet='deposit', event='Arsenal', stake=D('5'), odds=D('1.03'), player_id=self.player.id,
                         event_id=self.event.id, selection='home')
        self.assertEqual(sb.place_bet(wallet='deposit', event='Draw', stake=D('5'), odds=D('4.00'), player_id=self.player.id,
                                      event_id=self.event.id, selection='draw').status, 'accepting')

    def test_floor_is_adjustable_and_can_be_turned_off(self):
        LiveTradingSettings.objects.filter(pk=1).update(live_min_odds=0)
        self.feed(odds=SHORT_ODDS)
        self.assertEqual(self.bet(self.outcome('1.02')).status, 'accepting')

    def test_pre_match_prices_are_not_affected(self):
        Event.objects.filter(pk=self.event.pk).update(status='NS', starts_at=timezone.now() + timedelta(hours=2))
        short = Market.objects.create(event=self.event, key='over_under:ft:9.5', name='Over/Under', kind='over_under',
                                      line=D('9.5'))
        out = MarketOutcome.objects.create(market=short, key='under', label='Under 9.5', odds=D('1.01'))
        self.assertEqual(self.bet(out).status, 'open')

    def test_admin_sets_the_floor(self):
        staff = APIClient()
        staff.force_authenticate(User.objects.create_user('ops2', 'o2@example.com', 'x', is_staff=True))
        self.assertEqual(staff.get('/api/admin/sportsbook/live-trading/').json()['live_min_odds'], '1.05')
        self.assertEqual(staff.put('/api/admin/sportsbook/live-trading/', {'live_min_odds': '1.20'}, format='json').json()['live_min_odds'], '1.20')
        self.assertEqual(staff.put('/api/admin/sportsbook/live-trading/', {'live_min_odds': '0.5'}, format='json').status_code, 400)
        self.assertEqual(staff.put('/api/admin/sportsbook/live-trading/', {'live_min_odds': '0'}, format='json').status_code, 200)


class MoreDecidedCases(InPlayBase):
    def decided(self, kind, key, goals):
        self.event.score_home, self.event.score_away, self.event.status = *goals, '2H'
        market = Market(event=self.event, kind=kind, period='ft', metric='goals')
        return live_guard.outcome_decided(self.event, market, MarketOutcome(key=key))

    def test_win_to_nil(self):
        self.assertTrue(self.decided('win_to_nil_home', 'yes', (1, 1)))
        self.assertFalse(self.decided('win_to_nil_home', 'yes', (2, 0)))
        self.assertTrue(self.decided('win_to_nil_away', 'no', (1, 0)))

    def test_first_team_to_score(self):
        self.assertFalse(self.decided('first_team_to_score', 'home', (0, 0)))
        self.assertTrue(self.decided('first_team_to_score', 'none', (0, 1)))
        self.assertTrue(self.decided('first_team_to_score', 'home', (2, 0)))     # only home has scored
        self.assertFalse(self.decided('first_team_to_score', 'home', (1, 1)))    # who scored first unknown
