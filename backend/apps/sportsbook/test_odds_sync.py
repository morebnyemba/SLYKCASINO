"""Odds sync — pagination, league vs date sweeps, and unpriced imported fixtures."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings

from apps.accounts import services as account_services
from apps.sportsbook import services as sb
from apps.sportsbook.clients import ApiFootballClient, FixtureUpdate
from apps.sportsbook.models import Event
from apps.wallet import services as wallet_services


def _odds_row(fixture_id, home='2.10'):
    return {'fixture': {'id': fixture_id}, 'bookmakers': [{'bets': [{'name': 'Match Winner', 'values': [
        {'value': 'Home', 'odd': home}, {'value': 'Draw', 'odd': '3.30'}, {'value': 'Away', 'odd': '3.50'},
    ]}]}]}


def _page(rows, current, total):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {'errors': [], 'paging': {'current': current, 'total': total}, 'response': rows}
    return resp


@override_settings(API_FOOTBALL_KEY='k')
class OddsPaginationTests(TestCase):
    def test_follows_every_page(self):
        pages = [_page([_odds_row(1)], 1, 3), _page([_odds_row(2)], 2, 3), _page([_odds_row(3)], 3, 3)]
        with patch('apps.sportsbook.clients.requests.get', side_effect=pages) as get:
            snapshots = ApiFootballClient().fetch_odds(date='2026-09-28')
        self.assertEqual([s.external_id for s in snapshots], ['1', '2', '3'])
        self.assertEqual([c.kwargs['params']['page'] for c in get.call_args_list], [1, 2, 3])

    @override_settings(API_FOOTBALL_ODDS_MAX_PAGES=2)
    def test_respects_page_cap(self):
        pages = [_page([_odds_row(i)], i, 9) for i in range(1, 10)]
        with patch('apps.sportsbook.clients.requests.get', side_effect=pages) as get:
            ApiFootballClient().fetch_odds(date='2026-09-28')
        self.assertEqual(get.call_count, 2)

    def test_api_errors_stop_quietly(self):
        err = _page([], 1, 1)
        err.json.return_value = {'errors': {'requests': 'You have reached the request limit'}, 'response': []}
        with patch('apps.sportsbook.clients.requests.get', return_value=err):
            self.assertEqual(ApiFootballClient().fetch_odds(date='2026-09-28'), [])


class UpcomingOddsSweepTests(TestCase):
    @override_settings(API_FOOTBALL_LEAGUES=[39, 140], API_FOOTBALL_SEASON=2026)
    def test_by_league_when_configured(self):
        with patch.object(ApiFootballClient, 'fetch_odds', return_value=[]) as fetch:
            sb.sync_upcoming_odds()
        self.assertEqual(
            [(c.kwargs['league'], c.kwargs['season']) for c in fetch.call_args_list], [(39, 2026), (140, 2026)],
        )

    @override_settings(API_FOOTBALL_LEAGUES=[], API_FOOTBALL_ODDS_DAYS=2)
    def test_by_date_for_today_and_next_days_otherwise(self):
        with patch.object(ApiFootballClient, 'fetch_odds', return_value=[]) as fetch:
            sb.sync_upcoming_odds()
        self.assertEqual(len({c.kwargs['date'] for c in fetch.call_args_list}), 3)


class UnpricedEventTests(TestCase):
    def setUp(self):
        self.player = account_services.register_player(
            username='unpriced', email='unpriced@example.com', password='Passw0rd!', currency='USD',
        )
        wallet_services.credit(player_id=self.player.id, amount=Decimal('50'), kind='deposit', idempotency_key='u:dep')

    def test_imported_fixture_is_unpriced_until_odds_arrive(self):
        fixture = FixtureUpdate(external_id='501', name='A vs B', status='NS', starts_at=None,
                                goals_home=None, goals_away=None)
        event = sb._create_event_from_fixture(fixture)
        self.assertFalse(event.has_odds)
        with self.assertRaises(sb.SelectionUnavailable):
            sb.place_bet(event='A vs B — Home', stake=Decimal('5'), odds=Decimal('1.95'),
                         player_id=self.player.id, event_id=event.id, selection='home')

        with patch.object(ApiFootballClient, 'fetch_odds', return_value=[
            ApiFootballClient._normalize_odds(ApiFootballClient.__new__(ApiFootballClient), _odds_row(501)),
        ]):
            sb.sync_provider_odds(date='2026-09-28')
        event.refresh_from_db()
        self.assertTrue(event.has_odds)
        self.assertEqual(event.odds, Decimal('2.10'))
        bet = sb.place_bet(event='A vs B — Home', stake=Decimal('5'), odds=Decimal('2.10'),
                           player_id=self.player.id, event_id=event.id, selection='home')
        self.assertEqual(bet.odds, Decimal('2.10'))

    def test_manual_events_are_priced(self):
        self.assertTrue(Event.objects.create(name='Manual', odds=Decimal('1.80')).has_odds)


class EventListingTests(TestCase):
    """The player sportsbook asks for ?upcoming=true: bettable/live matches only,
    soonest first, and a whole board in one response via ?page_size=."""

    def setUp(self):
        from datetime import timedelta
        from django.utils import timezone
        now = timezone.now()
        mk = lambda name, hours, **kw: Event.objects.create(  # noqa: E731
            name=name, odds=Decimal('2'), starts_at=now + timedelta(hours=hours), **kw,
        )
        self.later = mk('Aaa later', 48)
        self.soon = mk('Zzz soon', 2)
        self.unpriced = mk('Mmm unpriced', 5, has_odds=False)
        self.live = mk('Live one', -1, is_open=False, status='2H')
        self.finished = mk('Finished', -5, is_open=False, status='FT')
        self.stale = mk('Stale open', -30)
        for i in range(30):
            mk(f'Filler {i:02}', 100 + i)

    def _get(self, query):
        from rest_framework.test import APIClient
        return APIClient().get(f'/api/events/{query}').data

    def test_upcoming_filters_and_orders_by_kickoff(self):
        data = self._get('?upcoming=true&page_size=200')
        names = [e['name'] for e in data['results']]
        self.assertEqual(names[:4], ['Live one', 'Zzz soon', 'Mmm unpriced', 'Aaa later'])
        self.assertNotIn('Finished', names)
        self.assertNotIn('Stale open', names)
        self.assertEqual(len(names), 34)
        self.assertIsNone(data['next'])

    def test_priced_filter_and_default_page_size(self):
        names = [e['name'] for e in self._get('?upcoming=true&priced=true&page_size=200')['results']]
        self.assertNotIn('Mmm unpriced', names)
        self.assertEqual(len(self._get('?upcoming=true')['results']), 25)


class ClosedEventBettingTests(TestCase):
    def test_1x2_bets_rejected_once_betting_closes(self):
        player = account_services.register_player(
            username='closed', email='closed@example.com', password='Passw0rd!', currency='USD',
        )
        wallet_services.credit(player_id=player.id, amount=Decimal('50'), kind='deposit', idempotency_key='c:dep')
        event = Event.objects.create(name='Closed v Match', odds=Decimal('2'), is_open=False)
        with self.assertRaises(sb.SelectionUnavailable):
            sb.place_bet(event='x', stake=Decimal('5'), odds=Decimal('2'), player_id=player.id,
                         event_id=event.id, selection='home')
