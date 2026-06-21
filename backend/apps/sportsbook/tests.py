"""sportsbook tests — event listing, bet placement, settlement."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services as account_services
from apps.livechat.clients import RealtimePublisherClient
from apps.sportsbook import services as sportsbook_services
from apps.sportsbook.models import Bet, BetSlip, Event
from apps.wallet import services as wallet_services


def _make_player(username='sbplayer', email='sb@example.com'):
    player = account_services.register_player(
        username=username, email=email, password='Passw0rd!', currency='USD',
    )
    wallet_services.credit(
        player_id=player.id, amount=Decimal('1000.00'),
        kind='deposit', idempotency_key=f'setup:sb:{player.id}',
    )
    return player


def _make_event(name='Test Match', odds=Decimal('2.00')):
    return Event.objects.create(name=name, odds=odds, is_open=True)


class EventListTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        _make_event('Event One')
        _make_event('Event Two')

    def test_event_list_public(self):
        resp = self.client.get('/api/events/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(resp.data), 2)


class BetPlacementTests(TestCase):
    def setUp(self):
        self.player = _make_player()
        self.event = _make_event()
        refresh = RefreshToken.for_user(self.player.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

    def test_bet_requires_auth(self):
        anon_client = APIClient()
        resp = anon_client.post('/api/bets/', {
            'event': 'Test Match', 'stake': '10.00', 'odds': '2.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_place_bet_debits_wallet(self):
        before = wallet_services.get_balance(self.player.id)
        resp = self.client.post('/api/bets/', {
            'event': 'Test Match', 'stake': '50.00', 'odds': '2.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        after = wallet_services.get_balance(self.player.id)
        self.assertEqual(before - after, Decimal('50.00'))

    def test_settle_bet_won_credits_wallet(self):
        bet = sportsbook_services.place_bet(
            event='Test Match', stake=Decimal('100.00'),
            odds=Decimal('2.00'), player_id=self.player.id,
        )
        before = wallet_services.get_balance(self.player.id)
        sportsbook_services.settle_bet(bet.id, 'won')
        after = wallet_services.get_balance(self.player.id)
        # Payout = 100 * 2.00 = 200
        self.assertEqual(after - before, Decimal('200.00'))

    def test_settle_bet_lost_no_credit(self):
        bet = sportsbook_services.place_bet(
            event='Test Match', stake=Decimal('50.00'),
            odds=Decimal('2.00'), player_id=self.player.id,
        )
        before = wallet_services.get_balance(self.player.id)
        sportsbook_services.settle_bet(bet.id, 'lost')
        after = wallet_services.get_balance(self.player.id)
        self.assertEqual(before, after)

    def test_settled_bet_has_correct_status(self):
        bet = sportsbook_services.place_bet(
            event='Test Match', stake=Decimal('10.00'),
            odds=Decimal('2.00'), player_id=self.player.id,
        )
        settled = sportsbook_services.settle_bet(bet.id, 'won')
        self.assertEqual(settled.status, Bet.Status.WON)


class SettleEventTests(TestCase):
    def setUp(self):
        self.player = _make_player(username='settler', email='settle@example.com')
        self.event = _make_event('Man Utd vs Arsenal')

    def _bet(self, selection, stake='50.00', odds='2.00'):
        return sportsbook_services.place_bet(
            event=f'Man Utd vs Arsenal — {selection}', stake=Decimal(stake), odds=Decimal(odds),
            player_id=self.player.id, event_id=self.event.id, selection=selection,
        )

    def test_settle_event_pays_matching_selection_only(self):
        home = self._bet('home')
        draw = self._bet('draw')
        away = self._bet('away')
        before = wallet_services.get_balance(self.player.id)

        count = sportsbook_services.settle_event(self.event.id, 'draw')

        self.assertEqual(count, 3)
        home.refresh_from_db(); draw.refresh_from_db(); away.refresh_from_db()
        self.assertEqual(draw.status, Bet.Status.WON)
        self.assertEqual(home.status, Bet.Status.LOST)
        self.assertEqual(away.status, Bet.Status.LOST)
        after = wallet_services.get_balance(self.player.id)
        # Only the 50.00 @ 2.00 draw bet pays out 100.00.
        self.assertEqual(after - before, Decimal('100.00'))

    def test_settle_event_void_refunds_all(self):
        self._bet('home'); self._bet('away')
        before = wallet_services.get_balance(self.player.id)
        sportsbook_services.settle_event(self.event.id, 'void')
        after = wallet_services.get_balance(self.player.id)
        # Two 50.00 stakes refunded.
        self.assertEqual(after - before, Decimal('100.00'))

    def test_settle_event_ignores_unlinked_bets(self):
        # A free-text bet with no event link must not be touched.
        sportsbook_services.place_bet(
            event='Some Other Match', stake=Decimal('20.00'), odds=Decimal('1.50'),
            player_id=self.player.id,
        )
        count = sportsbook_services.settle_event(self.event.id, 'home')
        self.assertEqual(count, 0)

    def test_settle_event_rejects_bad_result(self):
        with self.assertRaises(ValueError):
            sportsbook_services.settle_event(self.event.id, 'nonsense')


class AccumulatorTests(TestCase):
    def setUp(self):
        self.player = _make_player(username='accaplayer', email='acca@example.com')
        self.e1 = _make_event('Man Utd vs Arsenal', odds=Decimal('2.00'))
        self.e2 = _make_event('Lakers vs Warriors', odds=Decimal('3.00'))

    def _legs(self):
        return [
            {'event': 'Man Utd vs Arsenal', 'event_id': self.e1.id, 'selection': 'home', 'odds': '2.00'},
            {'event': 'Lakers vs Warriors', 'event_id': self.e2.id, 'selection': 'away', 'odds': '3.00'},
        ]

    def test_place_accumulator_debits_once_and_multiplies_odds(self):
        before = wallet_services.get_balance(self.player.id)
        slip = sportsbook_services.place_accumulator(
            stake=Decimal('10.00'), legs=self._legs(), player_id=self.player.id,
        )
        after = wallet_services.get_balance(self.player.id)
        self.assertEqual(before - after, Decimal('10.00'))      # single stake debit
        self.assertEqual(slip.combined_odds, Decimal('6.00'))   # 2.00 * 3.00
        self.assertEqual(slip.legs.count(), 2)
        self.assertEqual(slip.status, BetSlip.Status.OPEN)

    def test_accumulator_needs_two_legs(self):
        with self.assertRaises(ValueError):
            sportsbook_services.place_accumulator(
                stake=Decimal('10.00'), legs=self._legs()[:1], player_id=self.player.id,
            )

    def test_accumulator_wins_only_when_all_legs_win(self):
        slip = sportsbook_services.place_accumulator(
            stake=Decimal('10.00'), legs=self._legs(), player_id=self.player.id,
        )
        before = wallet_services.get_balance(self.player.id)
        sportsbook_services.settle_event(self.e1.id, 'home')   # leg 1 wins
        slip.refresh_from_db()
        self.assertEqual(slip.status, BetSlip.Status.OPEN)     # still open, leg 2 pending
        sportsbook_services.settle_event(self.e2.id, 'away')   # leg 2 wins -> acca wins
        slip.refresh_from_db()
        self.assertEqual(slip.status, BetSlip.Status.WON)
        after = wallet_services.get_balance(self.player.id)
        # Payout = 10 * 6.00 = 60
        self.assertEqual(after - before, Decimal('60.00'))

    def test_accumulator_loses_if_any_leg_loses(self):
        slip = sportsbook_services.place_accumulator(
            stake=Decimal('10.00'), legs=self._legs(), player_id=self.player.id,
        )
        before = wallet_services.get_balance(self.player.id)
        sportsbook_services.settle_event(self.e1.id, 'away')   # leg 1 loses (backed home)
        sportsbook_services.settle_event(self.e2.id, 'away')   # leg 2 wins, irrelevant
        slip.refresh_from_db()
        self.assertEqual(slip.status, BetSlip.Status.LOST)
        after = wallet_services.get_balance(self.player.id)
        self.assertEqual(before, after)                        # no payout

    def test_accumulator_api_create(self):
        refresh = RefreshToken.for_user(self.player.user)
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
        resp = client.post('/api/betslips/', {'stake': '5.00', 'legs': self._legs()}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['combined_odds'], '6.00')
        self.assertEqual(len(resp.data['legs']), 2)


class OddsPublishTests(TestCase):
    def test_saving_event_publishes_to_realtime(self):
        with patch('apps.livechat.clients.RealtimePublisherClient.publish') as pub:
            with self.captureOnCommitCallbacks(execute=True):
                ev = Event.objects.create(name='Pub Test', odds=Decimal('1.50'))
        self.assertTrue(pub.called)
        channels = [call.args[0] for call in pub.call_args_list]
        self.assertIn(f'odds:{ev.id}', channels)   # event-specific snapshot
        self.assertIn('odds', channels)             # global ticker line

    def test_publisher_disabled_is_noop(self):
        # REALTIME_PUBLISH_ENABLED is false in tests -> optimistic success, no network.
        self.assertTrue(RealtimePublisherClient().publish('odds:1', '{}'))


class ApiFootballSyncTests(TestCase):
    def setUp(self):
        self.player = _make_player(username='apifb', email='apifb@example.com')
        self.event = Event.objects.create(
            name='Chelsea vs Arsenal', odds=Decimal('2.00'),
            provider='api-football', external_id='12345',
        )

    def _fixture(self, status, goals_home=None, goals_away=None):
        from apps.sportsbook.clients import FixtureUpdate
        return FixtureUpdate(
            external_id='12345', name='Chelsea vs Arsenal', status=status,
            starts_at=None, goals_home=goals_home, goals_away=goals_away,
        )

    def test_client_noop_without_api_key(self):
        from apps.sportsbook.clients import ApiFootballClient
        self.assertEqual(ApiFootballClient().fetch_fixtures(live='all'), [])

    def test_sync_fixture_locks_betting_when_live(self):
        sportsbook_services.sync_fixture(self._fixture('1H'))
        self.event.refresh_from_db()
        self.assertFalse(self.event.is_open)

    def test_sync_fixture_settles_linked_bets_on_finish(self):
        bet = sportsbook_services.place_bet(
            event='Chelsea vs Arsenal — home', stake=Decimal('20.00'), odds=Decimal('2.00'),
            player_id=self.player.id, event_id=self.event.id, selection='home',
        )
        sportsbook_services.sync_fixture(self._fixture('FT', goals_home=2, goals_away=1))
        bet.refresh_from_db()
        self.event.refresh_from_db()
        self.assertEqual(bet.status, Bet.Status.WON)
        self.assertFalse(self.event.is_open)

    def test_sync_fixture_unlinked_external_id_is_noop(self):
        from apps.sportsbook.clients import FixtureUpdate
        result = sportsbook_services.sync_fixture(
            FixtureUpdate(external_id='nope', name='x', status='FT', starts_at=None,
                           goals_home=1, goals_away=0),
        )
        self.assertIsNone(result)

    def test_sync_fixture_upserts_linked_teams(self):
        from apps.sportsbook.clients import FixtureUpdate, TeamInfo
        from apps.sportsbook.models import Team
        fixture = FixtureUpdate(
            external_id='12345', name='Chelsea vs Arsenal', status='NS', starts_at=None,
            goals_home=None, goals_away=None,
            home_team=TeamInfo(external_id='t1', name='Chelsea', logo_url='https://x/c.png'),
            away_team=TeamInfo(external_id='t2', name='Arsenal', logo_url='https://x/a.png'),
        )
        sportsbook_services.sync_fixture(fixture)
        self.event.refresh_from_db()
        self.assertEqual(self.event.home_team.name, 'Chelsea')
        self.assertEqual(self.event.away_team.name, 'Arsenal')
        self.assertEqual(Team.objects.count(), 2)

        # Re-syncing the same fixture must not create duplicate Team rows.
        sportsbook_services.sync_fixture(fixture)
        self.assertEqual(Team.objects.count(), 2)


class ApiFootballOddsSyncTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(
            name='Chelsea vs Arsenal', odds=Decimal('1.50'),
            provider='api-football', external_id='999',
        )

    def _odds(self, home='2.10', draw='3.20', away='3.50'):
        from apps.sportsbook.clients import OddsSnapshot
        return OddsSnapshot(
            external_id='999', odds_home=Decimal(home),
            odds_draw=Decimal(draw) if draw is not None else None, odds_away=Decimal(away),
        )

    def test_sync_fixture_odds_updates_open_event(self):
        sportsbook_services.sync_fixture_odds(self._odds())
        self.event.refresh_from_db()
        self.assertEqual(self.event.odds, Decimal('2.10'))
        self.assertEqual(self.event.odds_draw, Decimal('3.20'))
        self.assertEqual(self.event.odds_away, Decimal('3.50'))

    def test_sync_fixture_odds_ignores_closed_event(self):
        self.event.is_open = False
        self.event.save(update_fields=['is_open'])
        result = sportsbook_services.sync_fixture_odds(self._odds())
        self.assertIsNone(result)
        self.event.refresh_from_db()
        self.assertEqual(self.event.odds, Decimal('1.50'))
