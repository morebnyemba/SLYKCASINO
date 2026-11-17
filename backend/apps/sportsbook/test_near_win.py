"""Near-win guard: no in-play bets on a pick the score and the clock have as good
as decided (near_win.py), greyed out on the boards."""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import SimpleTestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.sportsbook import live_guard, near_win
from apps.sportsbook import services as sb
from apps.sportsbook.models import LiveTradingSettings, MarketOutcome
from apps.sportsbook.test_in_play import FEED_ODDS, LIVE, InPlayBase, _v
from apps.sportsbook.test_keep_open import snapshot

D = Decimal


def p(status, elapsed, goals, kind, key, line=None, period='ft'):
    return near_win.win_probability(status=status, elapsed=elapsed, score_home=goals[0], score_away=goals[1],
                                    kind=kind, period=period, line=line, key=key)


class ModelTests(SimpleTestCase):
    def test_under_2_5_at_one_goal_depends_on_the_clock(self):
        early, late = p('1H', 10, (1, 0), 'over_under', 'under', D('2.5')), p('2H', 85, (1, 0), 'over_under', 'under', D('2.5'))
        self.assertLess(early, 0.4)          # a fair pick early on
        self.assertGreater(late, 0.95)       # two goals needed in ~9 minutes
        self.assertLess(p('2H', 60, (1, 0), 'over_under', 'under', D('2.5')),
                        p('2H', 75, (1, 0), 'over_under', 'under', D('2.5')))

    def test_settled_picks_are_certain_either_way(self):
        self.assertAlmostEqual(p('2H', 70, (2, 1), 'over_under', 'over', D('2.5')), 1.0, places=5)
        self.assertEqual(p('2H', 70, (2, 1), 'over_under', 'under', D('2.5')), 0.0)

    def test_covers_results_doubles_btts_and_combined_markets(self):
        self.assertGreater(p('2H', 88, (2, 0), 'match_result', 'home'), 0.99)
        self.assertGreater(p('2H', 85, (1, 0), 'double_chance', '1x'), 0.99)
        self.assertGreater(p('2H', 89, (1, 0), 'btts', 'no'), 0.9)
        self.assertGreater(p('2H', 89, (1, 0), 'result_total', 'home/under', D('2.5')), 0.9)
        self.assertLess(p('2H', 50, (1, 0), 'result_total', 'home/under', D('2.5')), 0.7)

    def test_first_half_markets_use_the_time_left_in_the_half(self):
        self.assertGreater(p('1H', 44, (0, 0), 'over_under', 'under', D('0.5'), period='1h'), 0.85)
        self.assertLess(p('1H', 44, (0, 0), 'over_under', 'under', D('0.5'), period='ft'), 0.3)
        self.assertIsNone(p('2H', 50, (0, 0), 'over_under', 'under', D('0.5'), period='1h'))   # the half is over

    def test_what_it_cannot_model_is_left_alone(self):
        self.assertIsNone(p('2H', 85, (1, 0), 'first_team_to_score', 'home'))     # needs the goal order
        self.assertIsNone(p('2H', 85, (1, 0), 'over_under', 'under', D('9.5'), period='2h'))
        self.assertIsNone(near_win.win_probability(status='2H', elapsed=85, score_home=1, score_away=0, kind='over_under',
                                                   period='ft', line=D('9.5'), key='under', metric='corners'))
        self.assertIsNone(p('NS', 0, (0, 0), 'over_under', 'under', D('2.5')))


# The under-2.5 price the feed still shows late on is generous (2.40), so the
# boards leave it for placement to refuse; the guard must catch it there.
STALE_UNDER = [
    {'id': 59, 'name': 'Fulltime Result', 'values': [_v('Home', '1.50'), _v('Draw', '4.00'), _v('Away', '7.00')]},
    {'id': 36, 'name': 'Over/Under Line', 'values': [_v('Over', '1.60', '2.5'), _v('Under', '2.40', '2.5')]},
    {'id': 69, 'name': 'Both Teams to Score', 'values': [_v('Yes', '2.20'), _v('No', '1.60')]},
]


@LIVE
class GuardTests(InPlayBase):
    def setUp(self):
        super().setUp()
        LiveTradingSettings.objects.filter(pk=1).update(keep_markets_open=True)

    def apply(self, **kw):
        return sb.apply_live_odds(snapshot(**kw), now=timezone.now())

    def outcome(self, market_key, key):
        return MarketOutcome.objects.get(market__event=self.event, market__key=market_key, key=key)

    def back(self, outcome):
        return sb.place_bet(wallet='deposit', event='x', stake=D('5'), odds=outcome.odds, player_id=self.player.id,
                            outcome_id=outcome.id)

    def test_default_is_on_at_90_percent(self):
        LiveTradingSettings.objects.all().delete()
        cfg = LiveTradingSettings.load()
        self.assertEqual((cfg.near_win_percent, cfg.near_win_goals_per_90), (90, D('2.70')))

    def test_under_2_5_at_1_0_late_is_refused_early_it_is_taken(self):
        self.apply(odds=STALE_UNDER, elapsed=20, goals=(1, 0))
        self.assertEqual(self.back(self.outcome('over_under:ft:2.5', 'under')).status, 'accepting')
        self.apply(odds=STALE_UNDER, elapsed=84, goals=(1, 0))
        under = self.outcome('over_under:ft:2.5', 'under')
        with self.assertRaisesMessage(sb.SelectionUnavailable, 'as good as decided'):
            self.back(under)
        # The side that still needs a goal stays open.
        self.assertEqual(self.back(self.outcome('over_under:ft:2.5', 'over')).status, 'accepting')

    def test_boards_grey_out_near_won_picks(self):
        self.apply(odds=FEED_ODDS, elapsed=89, goals=(1, 0))     # under 2.5 at 2.00, btts no at 1.60 (~93%)
        self.assertFalse(self.outcome('over_under:ft:2.5', 'under').is_open)
        self.assertFalse(self.outcome('btts:ft', 'no').is_open)
        self.assertTrue(self.outcome('over_under:ft:2.5', 'over').is_open)
        prices = sb.current_prices(event_ids=[], outcome_ids=[self.outcome('over_under:ft:2.5', 'under').id])
        self.assertFalse(next(iter(prices['outcomes'].values()))['open'])

    def test_a_near_won_match_result_is_greyed_out_and_refused(self):
        self.apply(elapsed=88, goals=(2, 0))
        self.event.refresh_from_db()
        state = sb.trading_state(self.event)
        self.assertEqual(state['main_blocked'], ['home'])
        with self.assertRaisesMessage(sb.SelectionUnavailable, 'as good as decided'):
            sb.place_bet(wallet='deposit', event='Arsenal', stake=D('5'), odds=self.event.odds, player_id=self.player.id,
                         event_id=self.event.id, selection='home')
        self.assertEqual(sb.place_bet(wallet='deposit', event='Draw', stake=D('5'), odds=self.event.odds_draw,
                                      player_id=self.player.id, event_id=self.event.id, selection='draw').status, 'accepting')
        frame = sb.current_prices(event_ids=[self.event.id], outcome_ids=[])['events'][self.event.id]
        self.assertEqual(frame['main_blocked'], ['home'])

    def test_a_pick_that_becomes_near_won_during_the_delay_is_rejected(self):
        self.apply(odds=STALE_UNDER, elapsed=60, goals=(1, 0))
        under = self.outcome('over_under:ft:2.5', 'under')
        bet = self.back(under)
        placed = bet.placed_at
        self.event.refresh_from_db()
        self.event.elapsed = 89
        self.event.save(update_fields=['elapsed'])
        reason = sb._live_recheck(event_id=self.event.id, selection='home', outcome_id=under.id, odds=under.odds,
                                  placed_at=placed, now=timezone.now())
        self.assertEqual(reason, 'the selection was as good as decided')

    def test_guard_can_be_turned_off(self):
        LiveTradingSettings.objects.filter(pk=1).update(near_win_percent=0)
        self.apply(odds=STALE_UNDER, elapsed=86, goals=(1, 0))
        self.assertEqual(self.back(self.outcome('over_under:ft:2.5', 'under')).status, 'accepting')
        self.event.refresh_from_db()
        self.assertEqual(sb.trading_state(self.event)['main_blocked'], [])

    def test_decided_still_wins_over_near_won(self):
        self.apply(elapsed=50, goals=(2, 1))
        self.event.refresh_from_db()
        self.assertTrue(live_guard.outcome_decided(
            self.event, self.outcome('over_under:ft:2.5', 'over').market, self.outcome('over_under:ft:2.5', 'over')))

    def test_admin_sets_the_guard(self):
        staff = APIClient()
        staff.force_authenticate(User.objects.create_user('nwops', 'nw@example.com', 'x', is_staff=True))
        url = '/api/admin/sportsbook/live-trading/'
        body = staff.get(url).json()
        self.assertEqual((body['near_win_percent'], body['near_win_goals_per_90']), (90, '2.70'))
        res = staff.put(url, {'near_win_percent': 85, 'near_win_goals_per_90': '3.1'}, format='json')
        self.assertEqual((res.json()['near_win_percent'], res.json()['near_win_goals_per_90']), (85, '3.10'))
        self.assertEqual(staff.put(url, {'near_win_percent': 40}, format='json').status_code, 400)
        self.assertEqual(staff.put(url, {'near_win_goals_per_90': '9'}, format='json').status_code, 400)
        self.assertEqual(staff.put(url, {'near_win_percent': 0}, format='json').status_code, 200)
