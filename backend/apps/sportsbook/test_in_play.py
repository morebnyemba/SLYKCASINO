"""In-play betting: the live odds feed, trading gates, the acceptance delay and
its re-checks (price, suspension, goals), and the knock-on for pre-match sync."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from apps.accounts import services as account_services
from apps.sportsbook import services as sb
from apps.sportsbook.clients import ApiFootballClient, FixtureUpdate, LiveOddsSnapshot, OddsSnapshot
from apps.sportsbook.market_feed import parse_live_odds
from apps.sportsbook.models import Bet, BetSlip, Event, Market, MarketOutcome
from apps.wallet import services as wallet_services

D = Decimal
LIVE = override_settings(SPORTSBOOK_LIVE_BETTING=True, SPORTSBOOK_LIVE_BET_DELAY=6, SPORTSBOOK_LIVE_ODDS_STALE=30)


def _v(value, odd, handicap=None, suspended=False):
    return {'value': value, 'odd': odd, 'handicap': handicap, 'main': None, 'suspended': suspended}


FEED_ODDS = [
    {'id': 59, 'name': 'Fulltime Result', 'values': [_v('Home', '1.50'), _v('Draw', '4.00'), _v('Away', '7.00')]},
    {'id': 36, 'name': 'Over/Under Line', 'values': [
        _v('Over', '1.80', '2.5'), _v('Under', '2.00', '2.5'),
        _v('Over', '3.10', '3.5'), _v('Under', '1.35', '3.5', suspended=True),
    ]},
    {'id': 69, 'name': 'Both Teams to Score', 'values': [_v('Yes', '2.20'), _v('No', '1.60')]},
    {'id': 33, 'name': 'Asian Handicap', 'values': [_v('Home', '1.90', '-0.5'), _v('Away', '1.90', '0.5')]},
    {'id': 18, 'name': '1x2 - 1st Half', 'values': [_v('Home', '2.00'), _v('Draw', '2.10'), _v('Away', '9.00')]},
]


class LiveParserTests(SimpleTestCase):
    def test_parses_traded_markets_and_folds_lines(self):
        one_x_two, markets = parse_live_odds(FEED_ODDS, first_half=True)
        self.assertEqual(one_x_two, (D('1.50'), D('4.00'), D('7.00')))
        keys = {m.key for m in markets}
        self.assertIn('over_under:ft:2.5', keys)
        self.assertIn('btts:ft', keys)
        self.assertIn('match_result:1h', keys)
        # A line with a suspended side can't be offered; handicaps aren't traded live.
        self.assertNotIn('over_under:ft:3.5', keys)
        self.assertFalse(any('handicap' in k for k in keys))

    def test_other_live_bets_come_in_as_manual_in_play_markets(self):
        odds = [*FEED_ODDS, {'id': 20, 'name': 'Next Goal', 'values': [
            _v('1', '1.70'), _v('No goal', '5.00'), _v('2', '2.40'),
        ]}]
        _, markets = parse_live_odds(odds, first_half=True, include_manual=True)
        by_key = {m.key: m for m in markets}
        # Live handicaps differ from the pre-match ones: their own manual row.
        handicap = by_key['manual:in_play_asian_handicap:ft']
        self.assertEqual((handicap.kind, handicap.name), ('manual', 'In play: Asian Handicap'))
        self.assertEqual([o.label for o in handicap.outcomes], ['Home -0.5', 'Away 0.5'])
        nxt = by_key['manual:in_play_next_goal:ft']
        self.assertEqual(len(nxt.outcomes), 3)
        self.assertIn('over_under:ft:2.5', by_key)  # recognised bets still settle automatically

    def test_first_half_markets_drop_after_the_break(self):
        _, markets = parse_live_odds(FEED_ODDS, first_half=False)
        self.assertNotIn('match_result:1h', {m.key for m in markets})

    def test_any_suspended_1x2_leg_suspends_the_1x2(self):
        odds = [{'name': 'Fulltime Result', 'values': [
            _v('Home', '1.50'), _v('Draw', '4.00', suspended=True), _v('Away', '7.00'),
        ]}]
        self.assertIsNone(parse_live_odds(odds)[0])

    def test_normalises_a_live_fixture(self):
        raw = {
            'fixture': {'id': 99, 'status': {'long': 'Second Half', 'elapsed': 63}},
            'teams': {'home': {'id': 1, 'goals': 1}, 'away': {'id': 2, 'goals': 0}},
            'status': {'stopped': False, 'blocked': True, 'finished': False},
            'odds': FEED_ODDS,
        }
        snap = ApiFootballClient()._normalize_live_odds(raw)
        self.assertEqual((snap.external_id, snap.elapsed, snap.goals_home, snap.goals_away), ('99', 63, 1, 0))
        self.assertTrue(snap.blocked)
        self.assertNotIn('match_result:1h', {m.key for m in snap.markets})


def _snapshot(fixture='555', *, home='1.50', goals=(0, 0), blocked=False, status='Second Half', odds=FEED_ODDS):
    one_x_two, markets = parse_live_odds(odds, first_half=status == 'First Half')
    if home is not None and one_x_two is not None:
        one_x_two = (D(home), one_x_two[1], one_x_two[2])
    return LiveOddsSnapshot(
        external_id=fixture, status=status, elapsed=60, goals_home=goals[0], goals_away=goals[1],
        blocked=blocked, one_x_two=one_x_two, markets=tuple(markets),
    )


class InPlayBase(TestCase):
    def setUp(self):
        self.t0 = timezone.now()
        self.event = Event.objects.create(
            name='Arsenal vs Chelsea', provider=ApiFootballClient.provider_name, external_id='555',
            starts_at=self.t0 - timedelta(minutes=60), status='2H', score_home=0, score_away=0,
            odds=D('2.00'), odds_draw=D('3.20'), odds_away=D('3.80'),
        )
        # A pre-match market the live feed doesn't carry.
        cs = Market.objects.create(event=self.event, key='correct_score:1h', name='1st half correct score',
                                   group='score', kind='correct_score', period='1h')
        self.pre_match_only = MarketOutcome.objects.create(market=cs, key='0:0', label='0-0', odds=D('3.00'))
        self.player = account_services.create_player(username='live_punter')
        wallet_services.credit(player_id=self.player.id, amount=D('100'), kind='deposit', idempotency_key='live:dep')

    def feed(self, at=None, **kw):
        return sb.apply_live_odds(_snapshot(**kw), now=at or timezone.now())

    def over_2_5(self):
        return MarketOutcome.objects.get(market__event=self.event, market__key='over_under:ft:2.5', key='over')


@LIVE
class LiveFeedTests(InPlayBase):
    def test_feed_prices_the_event_and_suspends_what_it_does_not_offer(self):
        self.feed()
        self.event.refresh_from_db()
        self.assertEqual((self.event.odds, self.event.odds_draw, self.event.odds_away), (D('1.50'), D('4.00'), D('7.00')))
        self.assertTrue(self.event.live_main_open)
        self.assertTrue(sb.in_play_bettable(self.event))
        self.assertTrue(Market.objects.get(event=self.event, key='btts:ft').is_open)
        self.assertFalse(Market.objects.get(event=self.event, key='correct_score:1h').is_open)
        self.assertEqual(sb.trading_state(self.event), {'in_play': True, 'bettable': True, 'main_open': True})

    def test_blocked_feed_suspends_and_goals_are_stamped(self):
        self.feed()
        self.feed(blocked=True, goals=(1, 0))
        self.event.refresh_from_db()
        self.assertIsNone(self.event.live_odds_at)
        self.assertFalse(sb.in_play_bettable(self.event))
        self.assertEqual((self.event.score_home, self.event.score_away), (1, 0))
        self.assertIsNotNone(self.event.last_goal_at)

    def test_stale_feed_suspends(self):
        self.feed(at=self.t0 - timedelta(seconds=45))
        self.event.refresh_from_db()
        self.assertFalse(sb.in_play_bettable(self.event))

    def test_operator_closed_event_is_not_traded(self):
        Event.objects.filter(pk=self.event.pk).update(is_open=False)
        self.feed()
        self.event.refresh_from_db()
        self.assertIsNone(self.event.live_odds_at)

    def test_pre_match_sync_leaves_live_prices_alone(self):
        self.feed()
        sb.sync_fixture_odds(OddsSnapshot(external_id='555', odds_home=D('9.99'), odds_draw=D('9.99'), odds_away=D('9.99')))
        self.event.refresh_from_db()
        self.assertEqual(self.event.odds, D('1.50'))

    def test_poll_skips_the_api_when_nothing_can_be_live(self):
        Event.objects.filter(pk=self.event.pk).update(status='FT')
        with patch.object(ApiFootballClient, 'fetch_live_odds') as fetch:
            self.assertEqual(sb.sync_live_odds(), 0)
        fetch.assert_not_called()
        Event.objects.filter(pk=self.event.pk).update(status='2H')
        with patch.object(ApiFootballClient, 'fetch_live_odds', return_value=[_snapshot()]) as fetch:
            self.assertEqual(sb.sync_live_odds(), 1)
        fetch.assert_called_once()

    def test_matches_dropped_from_the_feed_are_suspended(self):
        self.feed()
        with patch.object(ApiFootballClient, 'fetch_live_odds', return_value=[]):
            sb.sync_live_odds()
        self.event.refresh_from_db()
        self.assertIsNone(self.event.live_odds_at)
        self.assertFalse(sb.trading_state(self.event)['bettable'])

    def test_every_change_is_published_to_the_board(self):
        import json
        sent = []
        with patch('apps.livechat.clients.RealtimePublisherClient.publish',
                   side_effect=lambda channel, body: sent.append((channel, body))), \
                self.captureOnCommitCallbacks(execute=True):
            self.feed(goals=(1, 0))
        frames = [json.loads(body) for channel, body in sent if channel == sb.BOARD_CHANNEL]
        self.assertTrue(frames)
        last = frames[-1]
        self.assertEqual((last['event_id'], last['odds'], last['score_home']), (self.event.id, '1.50', 1))
        self.assertEqual((last['in_play'], last['main_open']), (True, True))

    def test_prices_endpoint(self):
        from rest_framework.test import APIClient
        self.feed()
        over = self.over_2_5()
        data = APIClient().get(
            f'/api/events/prices/?events={self.event.id}&outcomes={over.id},{self.pre_match_only.id}',
        ).json()
        self.assertEqual(data['events'][str(self.event.id)]['odds'], '1.50')
        self.assertTrue(data['events'][str(self.event.id)]['main_open'])
        self.assertEqual(data['outcomes'][str(over.id)], {'odds': '1.80', 'open': True})
        self.assertFalse(data['outcomes'][str(self.pre_match_only.id)]['open'])

    def test_lagging_fixture_poll_does_not_roll_back_the_live_score(self):
        self.feed(goals=(1, 0))
        self.event.refresh_from_db()
        stamped = self.event.last_goal_at
        sb.sync_fixture(FixtureUpdate(external_id='555', name='x', status='2H', starts_at=None,
                                      goals_home=0, goals_away=0))
        self.event.refresh_from_db()
        self.assertEqual((self.event.score_home, self.event.score_away, self.event.last_goal_at), (1, 0, stamped))

    def test_bets_awaiting_acceptance_are_rejected_once_the_match_is_over(self):
        self.feed()
        bet = sb.place_bet(event='Arsenal', stake=D('10'), odds=D('1.50'), player_id=self.player.id,
                           event_id=self.event.id, selection='home')
        Event.objects.filter(pk=self.event.pk).update(status='FT', starts_at=None)
        later = bet.placed_at + timedelta(seconds=8)
        self.assertEqual(sb.confirm_live_bet('bet', bet.id, now=later), 'rejected')

    def test_fixture_poll_keeps_in_play_matches_open(self):
        fixture = FixtureUpdate(external_id='555', name='Arsenal vs Chelsea', status='1H', starts_at=None,
                                goals_home=0, goals_away=0)
        sb.sync_fixture(fixture)
        self.event.refresh_from_db()
        self.assertTrue(self.event.is_open)
        sb.sync_fixture(FixtureUpdate(external_id='555', name='x', status='ET', starts_at=None,
                                      goals_home=1, goals_away=1))
        self.event.refresh_from_db()
        self.assertFalse(self.event.is_open)


@LIVE
class InPlayPlacementTests(InPlayBase):
    def place_over(self, odds='1.80', stake='10'):
        return sb.place_bet(event='Over 2.5', stake=D(stake), odds=D(odds), player_id=self.player.id,
                            outcome_id=self.over_2_5().id)

    def test_live_bet_holds_stake_while_accepting_then_opens(self):
        self.feed(at=self.t0)
        bet = self.place_over()
        self.assertEqual(bet.status, Bet.Status.ACCEPTING)
        self.assertEqual(wallet_services.get_balance(self.player.id), D('90'))
        # Too early: still inside the delay.
        self.assertEqual(sb.confirm_live_bet('bet', bet.id, now=bet.placed_at + timedelta(seconds=2)), 'accepting')
        # Feed hasn't refreshed since placement: wait rather than accept.
        self.assertEqual(sb.confirm_live_bet('bet', bet.id, now=bet.placed_at + timedelta(seconds=7)), 'accepting')
        later = bet.placed_at + timedelta(seconds=8)
        self.feed(at=later)
        self.assertEqual(sb.confirm_live_bet('bet', bet.id, now=later + timedelta(seconds=1)), 'open')
        self.assertEqual(wallet_services.get_balance(self.player.id), D('90'))

    def test_price_move_during_delay_rejects_and_refunds(self):
        self.feed(at=self.t0)
        bet = self.place_over()
        odds = [dict(b) for b in FEED_ODDS]
        odds[1] = {'name': 'Over/Under Line', 'values': [_v('Over', '1.60', '2.5'), _v('Under', '2.30', '2.5')]}
        later = bet.placed_at + timedelta(seconds=8)
        self.feed(at=later, odds=odds)
        self.assertEqual(sb.confirm_live_bet('bet', bet.id, now=later), 'rejected')
        self.assertEqual(wallet_services.get_balance(self.player.id), D('100'))
        # Idempotent.
        self.assertEqual(sb.confirm_live_bet('bet', bet.id, now=later), 'rejected')
        self.assertEqual(wallet_services.get_balance(self.player.id), D('100'))

    def test_goal_during_delay_rejects(self):
        self.feed(at=self.t0)
        bet = sb.place_bet(event='Arsenal', stake=D('10'), odds=D('1.50'), player_id=self.player.id,
                           event_id=self.event.id, selection='home')
        self.assertEqual(bet.status, Bet.Status.ACCEPTING)
        later = bet.placed_at + timedelta(seconds=8)
        self.feed(at=later, goals=(1, 0))  # same prices, but the score moved
        self.assertEqual(sb.confirm_live_bet('bet', bet.id, now=later), 'rejected')
        self.assertEqual(wallet_services.get_balance(self.player.id), D('100'))

    def test_feed_going_quiet_rejects(self):
        self.feed(at=self.t0)
        bet = self.place_over()
        self.assertEqual(sb.confirm_live_bet('bet', bet.id, now=bet.placed_at + timedelta(seconds=60)), 'rejected')

    def test_placement_checks_live_price_and_state(self):
        self.feed(at=self.t0)
        with self.assertRaises(sb.OddsChanged) as caught:
            sb.place_bet(event='Arsenal', stake=D('5'), odds=D('2.00'), player_id=self.player.id,
                         event_id=self.event.id, selection='home')
        self.assertEqual((caught.exception.event_id, caught.exception.selection), (self.event.id, 'home'))
        # A pre-match market the live feed doesn't offer is suspended in play.
        with self.assertRaises(sb.SelectionUnavailable):
            sb.place_bet(event='0-0', stake=D('5'), odds=D('3.00'), player_id=self.player.id,
                         outcome_id=self.pre_match_only.id)
        self.feed(blocked=True)
        with self.assertRaises(sb.SelectionUnavailable):
            self.place_over()

    def test_sweep_confirms_accepting_bets(self):
        self.feed(at=self.t0)
        bet = self.place_over()
        later = bet.placed_at + timedelta(seconds=8)
        self.feed(at=later)
        self.assertEqual(sb.confirm_accepting_bets(now=later + timedelta(seconds=1)), 1)
        bet.refresh_from_db()
        self.assertEqual(bet.status, Bet.Status.OPEN)

    def test_in_play_multiple(self):
        self.feed(at=self.t0)
        other = Event.objects.create(name='Pre vs Match', starts_at=self.t0 + timedelta(days=1),
                                     odds=D('2.0'), odds_draw=D('3.0'), odds_away=D('4.0'))
        slip = sb.place_accumulator(stake=D('10'), player_id=self.player.id, legs=[
            {'event': 'Over 2.5', 'odds': D('1.80'), 'outcome_id': self.over_2_5().id},
            {'event': 'Pre', 'odds': D('2.0'), 'event_id': other.id, 'selection': 'home'},
        ])
        self.assertEqual(slip.status, BetSlip.Status.ACCEPTING)
        later = slip.placed_at + timedelta(seconds=8)
        self.feed(at=later)
        self.assertEqual(sb.confirm_live_bet('slip', slip.id, now=later), 'open')

    def test_serialized_state(self):
        self.feed(at=self.t0)
        from rest_framework.test import APIClient
        data = APIClient().get(f'/api/events/{self.event.id}/').json()
        self.assertEqual((data['in_play'], data['bettable'], data['main_open']), (True, True, True))


@override_settings(SPORTSBOOK_LIVE_BETTING=False)
class LiveBettingOffTests(InPlayBase):
    def test_disabled_by_setting(self):
        sb.apply_live_odds(_snapshot(), now=timezone.now())
        with self.assertRaises(sb.SelectionUnavailable):
            sb.place_bet(event='Arsenal', stake=D('5'), odds=D('1.50'), player_id=self.player.id,
                         event_id=self.event.id, selection='home')
        with patch.object(ApiFootballClient, 'fetch_live_odds') as fetch:
            self.assertEqual(sb.sync_live_odds(), 0)
        fetch.assert_not_called()
