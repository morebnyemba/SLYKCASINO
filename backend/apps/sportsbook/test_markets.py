"""Secondary markets — feed parsing, score settlement rules, placement, settlement, API."""
from __future__ import annotations

from decimal import Decimal

from django.test import SimpleTestCase, TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services as account_services
from apps.sportsbook import services as sb
from apps.sportsbook.clients import ApiFootballClient, FixtureUpdate, OddsSnapshot
from apps.sportsbook.market_feed import FeedMarketData, FeedOutcome, parse_markets
from apps.sportsbook.models import Bet, BetLeg, BetSlip, Event, Market, MarketOutcome
from apps.sportsbook.settlement import Score, settle_outcome
from apps.wallet import services as wallet_services

D = Decimal


def _player(username):
    player = account_services.register_player(
        username=username, email=f'{username}@example.com', password='Passw0rd!', currency='USD',
    )
    wallet_services.credit(
        player_id=player.id, amount=D('1000.00'), kind='deposit', idempotency_key=f'setup:mk:{player.id}',
    )
    return player


def _market(event, kind, key, outcomes, *, line=None, period='ft', name=None):
    market = Market.objects.create(
        event=event, key=key, name=name or key, kind=kind, period=period, line=line,
    )
    for i, (okey, odds) in enumerate(outcomes):
        MarketOutcome.objects.create(market=market, key=okey, label=okey.title(), odds=D(odds), sort_order=i)
    return market


def _outcome(market, key):
    return market.outcomes.get(key=key)


class SettlementRuleTests(SimpleTestCase):
    def s(self, kind, key, score, line=None, period='ft'):
        return settle_outcome(kind=kind, period=period, line=line, key=key, score=score)

    def test_match_result_and_double_chance(self):
        sc = Score(2, 1)
        self.assertEqual(self.s('match_result', 'home', sc), 'won')
        self.assertEqual(self.s('match_result', 'draw', sc), 'lost')
        self.assertEqual(self.s('double_chance', '1x', sc), 'won')
        self.assertEqual(self.s('double_chance', 'x2', sc), 'lost')

    def test_draw_no_bet_voids_on_draw(self):
        self.assertEqual(self.s('draw_no_bet', 'home', Score(1, 1)), 'void')
        self.assertEqual(self.s('draw_no_bet', 'away', Score(0, 1)), 'won')

    def test_over_under_including_push(self):
        self.assertEqual(self.s('over_under', 'over', Score(2, 1), D('2.5')), 'won')
        self.assertEqual(self.s('over_under', 'under', Score(2, 1), D('2.5')), 'lost')
        self.assertEqual(self.s('over_under', 'over', Score(2, 1), D('3')), 'void')
        self.assertEqual(self.s('home_over_under', 'over', Score(2, 1), D('1.5')), 'won')
        self.assertEqual(self.s('away_over_under', 'over', Score(2, 1), D('1.5')), 'lost')

    def test_btts_clean_sheet_win_to_nil(self):
        self.assertEqual(self.s('btts', 'yes', Score(1, 1)), 'won')
        self.assertEqual(self.s('btts', 'no', Score(1, 0)), 'won')
        self.assertEqual(self.s('clean_sheet_home', 'yes', Score(1, 0)), 'won')
        self.assertEqual(self.s('win_to_nil_away', 'yes', Score(1, 0)), 'lost')
        self.assertEqual(self.s('win_to_nil_home', 'yes', Score(2, 0)), 'won')

    def test_asian_handicap(self):
        # Home -1.5 at 2-0: 2 - 1.5 > 0 -> home covers.
        self.assertEqual(self.s('asian_handicap', 'home', Score(2, 0), D('-1.5')), 'won')
        self.assertEqual(self.s('asian_handicap', 'away', Score(2, 0), D('-1.5')), 'lost')
        # Home -1 at 1-0 lands level -> push.
        self.assertEqual(self.s('asian_handicap', 'home', Score(1, 0), D('-1')), 'void')

    def test_handicap_result(self):
        # Home -1 at 2-1 -> adjusted 1-1 -> draw.
        self.assertEqual(self.s('handicap_result', 'draw', Score(2, 1), D('-1')), 'won')
        self.assertEqual(self.s('handicap_result', 'home', Score(2, 1), D('-1')), 'lost')

    def test_correct_score_exact_goals_odd_even(self):
        self.assertEqual(self.s('correct_score', '2:1', Score(2, 1)), 'won')
        self.assertEqual(self.s('correct_score', '1:1', Score(2, 1)), 'lost')
        self.assertEqual(self.s('exact_goals', '3', Score(2, 1)), 'won')
        self.assertEqual(self.s('exact_goals', '7+', Score(4, 3)), 'won')
        self.assertEqual(self.s('odd_even', 'odd', Score(2, 1)), 'won')

    def test_half_markets_need_half_time_score(self):
        self.assertIsNone(self.s('match_result', 'home', Score(2, 1), period='1h'))
        sc = Score(2, 1, 0, 1)
        self.assertEqual(self.s('match_result', 'away', sc, period='1h'), 'won')
        self.assertEqual(self.s('match_result', 'home', sc, period='2h'), 'won')  # 2-0 in 2nd half
        self.assertEqual(self.s('ht_ft', 'away/home', sc), 'won')
        self.assertEqual(self.s('highest_scoring_half', '2h', sc), 'won')

    def test_manual_markets_are_undecidable(self):
        self.assertIsNone(self.s('manual', 'over_9.5', Score(2, 1)))


class FeedParsingTests(SimpleTestCase):
    def test_splits_lines_and_normalises_keys(self):
        markets = parse_markets([
            {'name': 'Match Winner', 'values': [{'value': 'Home', 'odd': '2'}]},
            {'name': 'Goals Over/Under', 'values': [
                {'value': 'Over 2.5', 'odd': '1.9'}, {'value': 'Under 2.5', 'odd': '1.9'},
                {'value': 'Over 3.5', 'odd': '3.1'}, {'value': 'Under 3.5', 'odd': '1.3'},
            ]},
            {'name': 'Asian Handicap', 'values': [
                {'value': 'Home -1.5', 'odd': '2.5'}, {'value': 'Away +1.5', 'odd': '1.5'},
                {'value': 'Home -0.25', 'odd': '1.8'}, {'value': 'Away +0.25', 'odd': '2.0'},
            ]},
            {'name': 'Double Chance', 'values': [
                {'value': 'Home/Draw', 'odd': '1.2'}, {'value': 'Home/Away', 'odd': '1.3'},
                {'value': 'Draw/Away', 'odd': '1.6'},
            ]},
        ])
        by_key = {m.key: m for m in markets}
        self.assertNotIn('match_result:ft', by_key)  # 1X2 lives on the Event
        self.assertIn('over_under:ft:2.5', by_key)
        self.assertIn('over_under:ft:3.5', by_key)
        self.assertEqual(by_key['over_under:ft:2.5'].line, D('2.5'))
        self.assertIn('asian_handicap:ft:-1.5', by_key)
        self.assertFalse(any('-0.25' in k for k in by_key))  # quarter lines skipped
        self.assertEqual([o.key for o in by_key['double_chance:ft'].outcomes], ['1x', '12', 'x2'])

    def test_unknown_bets_become_manual_unless_disabled(self):
        bet = {'name': 'Player Shots On Target', 'values': [
            {'value': 'Over 1.5', 'odd': '1.8'}, {'value': 'Under 1.5', 'odd': '1.9'},
        ]}
        self.assertEqual(parse_markets([bet])[0].kind, 'manual')
        self.assertEqual(parse_markets([bet], include_manual=False), [])

    def test_client_normalize_odds_returns_markets(self):
        raw = {'fixture': {'id': 9}, 'bookmakers': [{'bets': [
            {'name': 'Match Winner', 'values': [
                {'value': 'Home', 'odd': '2.1'}, {'value': 'Draw', 'odd': '3.2'}, {'value': 'Away', 'odd': '3.4'},
            ]},
            {'name': 'Both Teams Score', 'values': [{'value': 'Yes', 'odd': '1.8'}, {'value': 'No', 'odd': '1.95'}]},
        ]}]}
        snapshot = ApiFootballClient._normalize_odds(ApiFootballClient.__new__(ApiFootballClient), raw)
        self.assertEqual(snapshot.odds_home, D('2.1'))
        self.assertEqual([m.key for m in snapshot.markets], ['btts:ft'])


class ApplyFeedMarketsTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(name='A v B', odds=D('2.00'), is_open=True)

    def _feed(self, over='1.90', under='1.90', include_btts=True):
        markets = [FeedMarketData(
            key='over_under:ft:2.5', name='Total goals 2.5', group='goals', kind='over_under',
            period='ft', line=D('2.5'), sort_order=1,
            outcomes=(FeedOutcome('over', 'Over 2.5', D(over)), FeedOutcome('under', 'Under 2.5', D(under))),
        )]
        if include_btts:
            markets.append(FeedMarketData(
                key='btts:ft', name='Both teams to score', group='main', kind='btts',
                period='ft', line=None, sort_order=0,
                outcomes=(FeedOutcome('yes', 'Yes', D('1.8')), FeedOutcome('no', 'No', D('1.95'))),
            ))
        return markets

    def test_upserts_tracks_price_moves_and_suspends_missing(self):
        sb.apply_feed_markets(self.event, self._feed())
        self.assertEqual(Market.objects.filter(event=self.event).count(), 2)

        sb.apply_feed_markets(self.event, self._feed(over='2.05', include_btts=False))
        over = MarketOutcome.objects.get(market__key='over_under:ft:2.5', key='over')
        self.assertEqual(over.odds, D('2.05'))
        self.assertEqual(over.previous_odds, D('1.90'))
        self.assertFalse(Market.objects.get(key='btts:ft').is_open)
        self.assertEqual(Market.objects.filter(event=self.event).count(), 2)  # nothing duplicated

    def test_sync_fixture_odds_applies_markets(self):
        self.event.provider, self.event.external_id = 'api-football', '77'
        self.event.save()
        sb.sync_fixture_odds(OddsSnapshot(
            external_id='77', odds_home=D('2.2'), odds_draw=D('3.1'), odds_away=D('3.3'),
            markets=tuple(self._feed()),
        ))
        self.assertEqual(self.event.markets.count(), 2)


class MarketBettingTests(TestCase):
    def setUp(self):
        self.player = _player('mkplayer')
        self.event = Event.objects.create(name='Chelsea v Arsenal', odds=D('2.00'), is_open=True)
        self.other = Event.objects.create(name='Spurs v Leeds', odds=D('1.50'), is_open=True)
        self.ou = _market(self.event, 'over_under', 'over_under:ft:2.5', [('over', '1.90'), ('under', '1.90')], line=D('2.5'))
        self.btts = _market(self.other, 'btts', 'btts:ft', [('yes', '1.80'), ('no', '2.00')])

    def _place(self, outcome, stake='10.00', odds=None):
        return sb.place_bet(
            event=f'{outcome.market.name} — {outcome.label}', stake=D(stake),
            odds=D(odds or str(outcome.odds)), player_id=self.player.id, outcome_id=outcome.id,
        )

    def test_bet_on_outcome_links_event_and_debits(self):
        before = wallet_services.get_balance(self.player.id)
        bet = self._place(_outcome(self.ou, 'over'))
        self.assertEqual(bet.event_ref_id, self.event.id)
        self.assertEqual(bet.outcome_ref.key, 'over')
        self.assertEqual(before - wallet_services.get_balance(self.player.id), D('10.00'))

    def test_stale_price_is_rejected(self):
        with self.assertRaises(sb.OddsChanged):
            self._place(_outcome(self.ou, 'over'), odds='2.10')
        self.assertEqual(Bet.objects.count(), 0)

    def test_suspended_market_is_rejected(self):
        self.ou.is_open = False
        self.ou.save()
        with self.assertRaises(sb.SelectionUnavailable):
            self._place(_outcome(self.ou, 'over'))

    def test_settle_from_score_pays_market_bets_and_leaves_1x2_logic_intact(self):
        over = self._place(_outcome(self.ou, 'over'))
        under = self._place(_outcome(self.ou, 'under'))
        home = sb.place_bet(
            event='Chelsea v Arsenal — home', stake=D('10.00'), odds=D('2.00'),
            player_id=self.player.id, event_id=self.event.id, selection='home',
        )
        before = wallet_services.get_balance(self.player.id)

        sb.settle_event_from_score(self.event.id, home=2, away=1)

        for bet in (over, under, home):
            bet.refresh_from_db()
        self.assertEqual(over.status, Bet.Status.WON)
        self.assertEqual(under.status, Bet.Status.LOST)
        self.assertEqual(home.status, Bet.Status.WON)
        # 10 @ 1.90 + 10 @ 2.00
        self.assertEqual(wallet_services.get_balance(self.player.id) - before, D('39.00'))
        self.ou.refresh_from_db()
        self.assertTrue(self.ou.settled)

    def test_settle_event_1x2_does_not_touch_market_bets(self):
        over = self._place(_outcome(self.ou, 'over'))
        sb.settle_event(self.event.id, 'home')
        over.refresh_from_db()
        self.assertEqual(over.status, Bet.Status.OPEN)

    def test_void_event_voids_market_bets(self):
        over = self._place(_outcome(self.ou, 'over'))
        before = wallet_services.get_balance(self.player.id)
        sb.settle_event(self.event.id, 'void')
        over.refresh_from_db()
        self.assertEqual(over.status, Bet.Status.VOID)
        self.assertEqual(wallet_services.get_balance(self.player.id) - before, D('10.00'))

    def test_accumulator_with_market_legs(self):
        slip = sb.place_accumulator(stake=D('10.00'), player_id=self.player.id, legs=[
            {'event': 'CvA Over 2.5', 'odds': '1.90', 'outcome_id': _outcome(self.ou, 'over').id},
            {'event': 'SvL BTTS yes', 'odds': '1.80', 'outcome_id': _outcome(self.btts, 'yes').id},
        ])
        self.assertEqual(slip.combined_odds, D('3.42'))
        sb.settle_event_from_score(self.event.id, home=3, away=0)
        slip.refresh_from_db()
        self.assertEqual(slip.status, BetSlip.Status.OPEN)  # BTTS leg still pending
        sb.settle_event_from_score(self.other.id, home=1, away=1)
        slip.refresh_from_db()
        self.assertEqual(slip.status, BetSlip.Status.WON)
        self.assertEqual(slip.payout, D('34.20'))
        self.assertTrue(all(leg.result == BetLeg.Result.WON for leg in slip.legs.all()))

    def test_accumulator_rejects_two_legs_on_one_event(self):
        with self.assertRaises(ValueError):
            sb.place_accumulator(stake=D('5.00'), player_id=self.player.id, legs=[
                {'event': 'CvA home', 'odds': '2.00', 'event_id': self.event.id, 'selection': 'home'},
                {'event': 'CvA over', 'odds': '1.90', 'outcome_id': _outcome(self.ou, 'over').id},
            ])

    def test_manual_market_settlement(self):
        corners = _market(self.event, 'manual', 'manual:corners:ft', [('over_9.5', '1.80'), ('under_9.5', '1.95')])
        bet = self._place(_outcome(corners, 'over_9.5'))
        sb.settle_event_from_score(self.event.id, home=0, away=0)
        bet.refresh_from_db()
        self.assertEqual(bet.status, Bet.Status.OPEN)  # can't be settled from the score
        sb.settle_market_manually(corners.id, winners=[_outcome(corners, 'over_9.5').id])
        bet.refresh_from_db()
        self.assertEqual(bet.status, Bet.Status.WON)

    def test_sync_fixture_settles_markets_on_regulation_score(self):
        self.event.provider, self.event.external_id = 'api-football', '555'
        self.event.save()
        ht = _market(self.event, 'match_result', 'match_result:1h', [('home', '3'), ('draw', '2'), ('away', '4')], period='1h')
        over = self._place(_outcome(self.ou, 'over'))
        ht_draw = self._place(_outcome(ht, 'draw'))
        # 1-1 after 90', 3-1 after extra time: markets settle on the 90' score.
        sb.sync_fixture(FixtureUpdate(
            external_id='555', name='x', status='AET', starts_at=None, goals_home=3, goals_away=1,
            ht_home=0, ht_away=0, ft_home=1, ft_away=1,
        ))
        over.refresh_from_db(); ht_draw.refresh_from_db()
        self.assertEqual(over.status, Bet.Status.LOST)
        self.assertEqual(ht_draw.status, Bet.Status.WON)
        self.event.refresh_from_db()
        self.assertEqual((self.event.score_home, self.event.score_away), (1, 1))


class MarketApiTests(TestCase):
    def setUp(self):
        self.player = _player('mkapi')
        self.event = Event.objects.create(name='Chelsea v Arsenal', odds=D('2.00'), is_open=True)
        self.ou = _market(self.event, 'over_under', 'over_under:ft:2.5', [('over', '1.90'), ('under', '1.90')], line=D('2.5'))
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(self.player.user).access_token}')

    def test_list_has_markets_count_and_detail_has_markets(self):
        listing = APIClient().get('/api/events/')
        row = next(r for r in (listing.data.get('results', listing.data)) if r['id'] == self.event.id)
        self.assertEqual(row['markets_count'], 1)
        detail = APIClient().get(f'/api/events/{self.event.id}/')
        self.assertEqual(detail.data['markets'][0]['key'], 'over_under:ft:2.5')
        self.assertEqual(len(detail.data['markets'][0]['outcomes']), 2)

    def test_place_bet_on_outcome_via_api(self):
        over = _outcome(self.ou, 'over')
        resp = self.client.post('/api/bets/', {
            'event': 'Chelsea v Arsenal — Over 2.5', 'outcome_id': over.id, 'stake': '5.00', 'odds': '1.90',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertEqual(resp.data['market_name'], 'over_under:ft:2.5')
        self.assertEqual(resp.data['outcome_label'], 'Over')

    def test_stale_price_returns_409_with_current_odds(self):
        over = _outcome(self.ou, 'over')
        resp = self.client.post('/api/bets/', {
            'event': 'x', 'outcome_id': over.id, 'stake': '5.00', 'odds': '2.50',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_409_CONFLICT)
        self.assertEqual(resp.data['code'], 'odds_changed')
        self.assertEqual(resp.data['odds'], '1.90')

    def test_1x2_bet_serializes_null_market_labels(self):
        resp = self.client.post('/api/bets/', {
            'event': 'Chelsea v Arsenal — home', 'event_id': self.event.id, 'selection': 'home',
            'stake': '5.00', 'odds': '2.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED, resp.data)
        self.assertIsNone(resp.data['market_name'])

    def test_admin_settle_endpoints(self):
        staff = _player('mkstaff')
        staff.user.is_staff = True
        staff.user.save()
        admin = APIClient()
        admin.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(staff.user).access_token}')

        self.assertEqual(
            self.client.post(f'/api/events/{self.event.id}/settle-score/', {'home': 1, 'away': 0}).status_code,
            status.HTTP_403_FORBIDDEN,
        )
        bad = admin.post(f'/api/events/{self.event.id}/settle-score/', {'home': 1}, format='json')
        self.assertEqual(bad.status_code, status.HTTP_400_BAD_REQUEST)
        ok = admin.post(f'/api/events/{self.event.id}/settle-score/', {'home': 3, 'away': 1}, format='json')
        self.assertEqual(ok.status_code, status.HTTP_200_OK, ok.data)
        self.assertEqual(_outcome(self.ou, 'over').result, MarketOutcome.Result.WON)

        corners = _market(self.event, 'manual', 'manual:corners:ft', [('over_9.5', '1.80'), ('under_9.5', '1.95')])
        resp = admin.post(
            f'/api/events/{self.event.id}/markets/{corners.id}/settle/', {'void': True}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_200_OK, resp.data)
        self.assertTrue(all(o.result == 'void' for o in corners.outcomes.all()))
