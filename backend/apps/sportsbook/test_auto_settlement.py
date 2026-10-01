"""Automatic settlement of stats/event-based markets: corners, cards, goalscorers,
first/last team to score, result combos — and the finished-fixture poll."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.accounts import services as account_services
from apps.sportsbook import services as sb
from apps.sportsbook.clients import FixtureUpdate, normalize_facts
from apps.sportsbook.market_feed import parse_markets
from apps.sportsbook.models import Bet, Event, Market, MarketOutcome
from apps.sportsbook.settlement import GoalEvent, Score, same_player, settle_outcome
from apps.wallet import services as wallet_services

D = Decimal

# 2-1 home win, half-time 0-1. Away scored first (own goal by a home defender),
# then Fernandes (pen) and Rashford for the home side.
GOALS = (
    GoalEvent(20, 'away', 'H. Maguire', own_goal=True),
    GoalEvent(55, 'home', 'B. Fernandes', penalty=True),
    GoalEvent(88, 'home', 'M. Rashford'),
)
FACTS = Score(
    2, 1, 0, 1, corners=(7, 4), cards=(3, 2), reds=(0, 1), goals=GOALS,
    participants=('H. Maguire', 'B. Fernandes', 'M. Rashford', 'B. Saka', 'M. Odegaard'),
)


class StatsRuleTests(SimpleTestCase):
    def s(self, kind, key, score=FACTS, line=None, metric='goals', period='ft', label=''):
        return settle_outcome(kind=kind, period=period, line=line, key=key, score=score, metric=metric, label=label)

    def test_corners_and_cards(self):
        self.assertEqual(self.s('over_under', 'over', line=D('9.5'), metric='corners'), 'won')   # 11
        self.assertEqual(self.s('home_over_under', 'under', line=D('6.5'), metric='corners'), 'lost')
        self.assertEqual(self.s('match_result', 'home', metric='corners'), 'won')
        self.assertEqual(self.s('asian_handicap', 'away', line=D('-3.5'), metric='corners'), 'won')  # 7-3.5 < 4
        self.assertEqual(self.s('over_under', 'over', line=D('4.5'), metric='cards'), 'won')     # 5
        self.assertEqual(self.s('over_under', 'under', line=D('5'), metric='cards'), 'void')
        self.assertEqual(self.s('red_card', 'yes'), 'won')

    def test_stats_markets_wait_for_stats_and_ignore_extra_time(self):
        bare = Score(2, 1)
        self.assertIsNone(self.s('over_under', 'over', bare, D('9.5'), 'corners'))
        self.assertIsNone(self.s('red_card', 'no', bare))
        et = Score(1, 1, corners=(8, 8), extra_time=True)
        self.assertIsNone(self.s('over_under', 'over', et, D('9.5'), 'corners'))

    def test_goalscorers(self):
        self.assertEqual(self.s('anytime_scorer', 'x', label='Bruno Fernandes'), 'won')
        self.assertEqual(self.s('anytime_scorer', 'x', label='Bukayo Saka'), 'lost')          # played, no goal
        self.assertEqual(self.s('anytime_scorer', 'x', label='Gabriel Jesus'), 'void')        # didn't play
        self.assertEqual(self.s('anytime_scorer', 'x', label='Harry Maguire'), 'lost')        # own goal doesn't count
        # First scorer ignores the own goal: Fernandes' penalty is the first real goal.
        self.assertEqual(self.s('first_scorer', 'x', label='Bruno Fernandes'), 'won')
        self.assertEqual(self.s('last_scorer', 'x', label='Marcus Rashford'), 'won')
        self.assertEqual(self.s('anytime_scorer', 'none'), 'lost')
        self.assertEqual(self.s('anytime_scorer', 'none', Score(0, 0, goals=())), 'won')
        # Without lineups a non-scorer can't be told apart from a non-starter.
        no_lineup = Score(2, 1, goals=GOALS)
        self.assertIsNone(self.s('anytime_scorer', 'x', no_lineup, label='Bukayo Saka'))

    def test_goal_events_must_match_score(self):
        wrong = Score(3, 1, goals=GOALS)
        self.assertIsNone(self.s('anytime_scorer', 'x', wrong, label='Bruno Fernandes'))
        self.assertIsNone(self.s('first_team_to_score', 'home', wrong))

    def test_first_last_team_and_own_goal(self):
        self.assertEqual(self.s('first_team_to_score', 'away'), 'won')
        self.assertEqual(self.s('last_team_to_score', 'home'), 'won')
        self.assertEqual(self.s('first_team_to_score', 'none', Score(0, 0)), 'won')
        self.assertEqual(self.s('own_goal', 'yes'), 'won')

    def test_combos_and_halves(self):
        self.assertEqual(self.s('result_btts', 'home/yes'), 'won')
        self.assertEqual(self.s('result_btts', 'home/no'), 'lost')
        self.assertEqual(self.s('result_total', 'home/under', line=D('3.5')), 'won')
        self.assertEqual(self.s('result_total', 'home/over', line=D('3')), 'void')
        self.assertEqual(self.s('result_total', 'draw/over', line=D('1.5')), 'lost')
        self.assertEqual(self.s('win_either_half', 'home'), 'won')     # 2nd half 2-0
        self.assertEqual(self.s('win_both_halves', 'home'), 'lost')
        self.assertEqual(self.s('score_both_halves', 'away'), 'lost')  # away scored only in the 1st
        self.assertEqual(self.s('home_exact_goals', '2'), 'won')
        self.assertEqual(self.s('team_to_score_away', 'yes'), 'won')
        self.assertEqual(self.s('win_to_nil', 'home'), 'lost')
        self.assertEqual(self.s('double_chance', 'x2', period='1h'), 'won')

    def test_player_name_matching(self):
        self.assertTrue(same_player('Bruno Fernandes', 'B. Fernandes'))
        self.assertTrue(same_player('Virgil van Dijk', 'V. van Dijk'))
        self.assertTrue(same_player('Vinícius Júnior', 'Vinicius Junior'))
        self.assertFalse(same_player('Bruno Fernandes', 'J. Fernandes'))
        self.assertFalse(same_player('Bruno Fernandes', 'B. Silva'))


SAMPLE_FIXTURE = {
    'fixture': {'id': 999, 'status': {'short': 'FT', 'elapsed': 90}, 'date': '2026-09-27T15:00:00+00:00'},
    'teams': {'home': {'id': 33, 'name': 'Man Utd'}, 'away': {'id': 42, 'name': 'Arsenal'}},
    'goals': {'home': 2, 'away': 1},
    'score': {'halftime': {'home': 0, 'away': 1}, 'fulltime': {'home': 2, 'away': 1}},
    'events': [
        # api-football lists an own goal under the scorer's team; the loader flips it.
        {'time': {'elapsed': 20}, 'team': {'id': 33}, 'player': {'name': 'H. Maguire'}, 'type': 'Goal', 'detail': 'Own Goal'},
        {'time': {'elapsed': 40}, 'team': {'id': 42}, 'player': {'name': 'B. Saka'}, 'type': 'Card', 'detail': 'Yellow Card'},
        {'time': {'elapsed': 55}, 'team': {'id': 33}, 'player': {'name': 'B. Fernandes'}, 'type': 'Goal', 'detail': 'Penalty'},
        {'time': {'elapsed': 70}, 'team': {'id': 42}, 'player': {'name': 'G. Martinelli'}, 'type': 'Goal', 'detail': 'Missed Penalty'},
        {'time': {'elapsed': 75}, 'team': {'id': 33}, 'player': {'name': 'A. Garnacho'},
         'assist': {'name': 'M. Mount'}, 'type': 'subst', 'detail': 'Substitution 1'},
        {'time': {'elapsed': 90, 'extra': 3}, 'team': {'id': 33}, 'player': {'name': 'M. Rashford'}, 'type': 'Goal', 'detail': 'Normal Goal'},
    ],
    'statistics': [
        {'team': {'id': 33}, 'statistics': [
            {'type': 'Corner Kicks', 'value': 7}, {'type': 'Yellow Cards', 'value': 3}, {'type': 'Red Cards', 'value': None},
        ]},
        {'team': {'id': 42}, 'statistics': [
            {'type': 'Corner Kicks', 'value': 4}, {'type': 'Yellow Cards', 'value': 1}, {'type': 'Red Cards', 'value': 1},
        ]},
    ],
    'lineups': [
        {'team': {'id': 33}, 'startXI': [{'player': {'name': 'H. Maguire'}}, {'player': {'name': 'B. Fernandes'}},
                                         {'player': {'name': 'M. Rashford'}}, {'player': {'name': 'M. Mount'}}]},
        {'team': {'id': 42}, 'startXI': [{'player': {'name': 'B. Saka'}}, {'player': {'name': 'G. Martinelli'}}]},
    ],
}


class FactsLoadingTests(TestCase):
    def test_normalize_facts(self):
        facts = normalize_facts(SAMPLE_FIXTURE)
        self.assertEqual(facts['corners'], [7, 4])
        self.assertEqual(facts['yellow'], [3, 1])
        self.assertEqual(facts['red'], [0, 1])
        self.assertEqual([g['player'] for g in facts['goals']], ['H. Maguire', 'B. Fernandes', 'M. Rashford'])
        self.assertIn('A. Garnacho', facts['participants'])  # came off the bench
        self.assertFalse(facts['extra_time'])

    def test_score_for_event_fixes_own_goal_attribution(self):
        event = Event.objects.create(
            name='Man Utd vs Arsenal', odds=D('2'), score_home=2, score_away=1, ht_score_home=0, ht_score_away=1,
            match_facts=normalize_facts(SAMPLE_FIXTURE),
        )
        score = sb.score_for_event(event)
        self.assertEqual([g.side for g in score.goal_events], ['away', 'home', 'home'])
        self.assertEqual(score.cards, (3, 2))


class FinishedFixturePollTests(TestCase):
    def setUp(self):
        self.player = account_services.register_player(
            username='autosettle', email='auto@example.com', password='Passw0rd!', currency='USD',
        )
        wallet_services.credit(player_id=self.player.id, amount=D('100'), kind='deposit', idempotency_key='auto:dep')
        self.event = Event.objects.create(
            name='Man Utd vs Arsenal', odds=D('2.00'), odds_draw=D('3.40'), odds_away=D('3.80'),
            provider='api-football', external_id='999', starts_at=timezone.now() - timedelta(hours=3),
        )
        bets = [
            {'name': 'Corners Over Under', 'values': [{'value': 'Over 9.5', 'odd': '1.90'}, {'value': 'Under 9.5', 'odd': '1.90'}]},
            {'name': 'Anytime Goal Scorer', 'values': [{'value': 'Bruno Fernandes', 'odd': '3.00'}, {'value': 'Bukayo Saka', 'odd': '3.50'}]},
            {'name': 'Team To Score First', 'values': [{'value': 'Home', 'odd': '1.70'}, {'value': 'Draw', 'odd': '9.00'}, {'value': 'Away', 'odd': '2.50'}]},
        ]
        sb.apply_feed_markets(self.event, parse_markets(bets))

    def _before_kickoff(self, place):
        """Bets close at kick-off, so place them as if the match hadn't started yet."""
        with patch('apps.sportsbook.services.timezone.now', return_value=timezone.now() - timedelta(hours=4)):
            return place()

    def _bet(self, market_key, outcome_key):
        outcome = MarketOutcome.objects.get(market__key=market_key, key=outcome_key)
        return self._before_kickoff(lambda: sb.place_bet(
            event='x', stake=D('10'), odds=outcome.odds, player_id=self.player.id, outcome_id=outcome.id,
        ))

    def _fixture(self, raw):
        from apps.sportsbook.clients import ApiFootballClient
        return ApiFootballClient.__new__(ApiFootballClient)._normalize(raw)

    def test_poll_settles_everything_including_stats_markets(self):
        home = self._before_kickoff(lambda: sb.place_bet(
            event='x', stake=D('10'), odds=D('2.00'), player_id=self.player.id,
            event_id=self.event.id, selection='home'))
        corners = self._bet('over_under:corners:ft:9.5', 'over')
        fernandes = self._bet('anytime_scorer:ft', 'bruno_fernandes')
        saka = self._bet('anytime_scorer:ft', 'bukayo_saka')
        first = self._bet('first_team_to_score:ft', 'away')

        self.assertIn(self.event, sb.events_awaiting_settlement())
        with patch('apps.sportsbook.clients.ApiFootballClient.fetch_fixtures_by_ids',
                   return_value=[self._fixture(SAMPLE_FIXTURE)]):
            self.assertEqual(sb.settle_finished_fixtures(), 1)

        for bet in (home, corners, fernandes, saka, first):
            bet.refresh_from_db()
        self.assertEqual(home.status, Bet.Status.WON)
        self.assertEqual(corners.status, Bet.Status.WON)
        self.assertEqual(fernandes.status, Bet.Status.WON)
        self.assertEqual(saka.status, Bet.Status.LOST)
        self.assertEqual(first.status, Bet.Status.WON)  # own goal credited to Arsenal
        self.assertFalse(Market.objects.filter(event=self.event, settled=False).exists())
        self.assertNotIn(self.event, sb.events_awaiting_settlement())

    def test_markets_wait_for_stats_then_settle_on_a_later_poll(self):
        corners = self._bet('over_under:corners:ft:9.5', 'over')
        bare = {k: v for k, v in SAMPLE_FIXTURE.items() if k not in ('events', 'statistics', 'lineups')}
        with patch('apps.sportsbook.clients.ApiFootballClient.fetch_fixtures_by_ids',
                   return_value=[self._fixture(bare)]):
            sb.settle_finished_fixtures()
        corners.refresh_from_db()
        self.assertEqual(corners.status, Bet.Status.OPEN)
        self.assertIn(self.event, sb.events_awaiting_settlement())  # retried next run

        with patch('apps.sportsbook.clients.ApiFootballClient.fetch_fixtures_by_ids',
                   return_value=[self._fixture(SAMPLE_FIXTURE)]):
            sb.settle_finished_fixtures()
        corners.refresh_from_db()
        self.assertEqual(corners.status, Bet.Status.WON)

    def test_cancelled_fixture_voids_everything(self):
        corners = self._bet('over_under:corners:ft:9.5', 'over')
        cancelled = dict(SAMPLE_FIXTURE, fixture={'id': 999, 'status': {'short': 'CANC'}},
                         goals={'home': None, 'away': None}, score={})
        before = wallet_services.get_balance(self.player.id)
        with patch('apps.sportsbook.clients.ApiFootballClient.fetch_fixtures_by_ids',
                   return_value=[self._fixture(cancelled)]):
            sb.settle_finished_fixtures()
        corners.refresh_from_db()
        self.assertEqual(corners.status, Bet.Status.VOID)
        self.assertEqual(wallet_services.get_balance(self.player.id) - before, D('10'))

    def test_operator_settlement_with_corner_counts(self):
        corners = self._bet('over_under:corners:ft:9.5', 'over')
        sb.settle_event_from_score(self.event.id, home=1, away=0, corners=(3, 4))
        corners.refresh_from_db()
        self.assertEqual(corners.status, Bet.Status.LOST)
        # Scorer markets can't settle without goal events: flagged for review.
        self.assertTrue(Market.objects.get(event=self.event, key='anytime_scorer:ft').needs_review)


class FixturePayloadTests(SimpleTestCase):
    def test_fixture_update_carries_facts(self):
        from apps.sportsbook.clients import ApiFootballClient
        fixture = ApiFootballClient.__new__(ApiFootballClient)._normalize(SAMPLE_FIXTURE)
        self.assertIsInstance(fixture, FixtureUpdate)
        self.assertEqual(fixture.facts['corners'], [7, 4])
        self.assertEqual(fixture.result, 'home')
