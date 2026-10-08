"""Operator console API: feed settings (write-only key), leagues, hand-edited
matches with a price lock the feeds respect, and the overview stats."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.sportsbook import services as sb
from apps.sportsbook.clients import ApiFootballClient, OddsSnapshot
from apps.sportsbook.models import Bet, Event, LeagueSetting, ProviderCredential

D = Decimal


class AdminApiBase(TestCase):
    def setUp(self):
        self.staff = User.objects.create(username='ops', is_staff=True)
        self.api = APIClient()
        self.api.force_authenticate(self.staff)


class PermissionTests(TestCase):
    def test_players_are_refused(self):
        api = APIClient()
        api.force_authenticate(User.objects.create(username='punter'))
        for url in ('/api/admin/sportsbook/feed/', '/api/admin/sportsbook/events/', '/api/admin/sportsbook/leagues/'):
            self.assertEqual(api.get(url).status_code, 403, url)


@override_settings(API_FOOTBALL_KEY='')
class FeedSettingsTests(AdminApiBase):
    def test_key_is_write_only_and_masked(self):
        res = self.api.put('/api/admin/sportsbook/feed/', {'api_key': 'abcd1234efgh5678'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        body = res.json()
        self.assertEqual((body['has_key'], body['key_hint'], body['key_source']), (True, '••••5678', 'console'))
        self.assertNotIn('abcd1234efgh5678', res.content.decode())
        self.assertEqual(ProviderCredential.objects.get().api_key, 'abcd1234efgh5678')
        # Blank key leaves it alone; clear_key removes it.
        self.api.put('/api/admin/sportsbook/feed/', {'api_key': '', 'base_url': 'https://v3.football.api-sports.io/'}, format='json')
        self.assertEqual(ProviderCredential.objects.get().api_key, 'abcd1234efgh5678')
        self.assertEqual(ProviderCredential.objects.get().base_url, 'https://v3.football.api-sports.io')
        self.assertFalse(self.api.put('/api/admin/sportsbook/feed/', {'clear_key': True}, format='json').json()['has_key'])

    def test_bad_base_url(self):
        self.assertEqual(self.api.put('/api/admin/sportsbook/feed/', {'base_url': 'ftp://x'}, format='json').status_code, 400)

    def test_connection_test_reports_errors(self):
        self.assertEqual(self.api.post('/api/admin/sportsbook/feed/test/').json(), {'ok': False, 'error': 'No API key is set.'})
        ProviderCredential.objects.create(provider='api-football', api_key='k' * 20)
        payload = {'errors': [], 'response': {
            'account': {'firstname': 'Ops', 'lastname': 'Team', 'email': 'ops@example.com'},
            'subscription': {'plan': 'Pro', 'active': True, 'end': '2027-01-01'},
            'requests': {'current': 120, 'limit_day': 7500}}}
        with patch('apps.sportsbook.clients.requests.get') as get:
            get.return_value.json.return_value = payload
            get.return_value.raise_for_status.return_value = None
            body = self.api.post('/api/admin/sportsbook/feed/test/').json()
        self.assertEqual((body['ok'], body['plan'], body['requests_today'], body['requests_limit']), (True, 'Pro', 120, 7500))

    def test_sync_queues_known_jobs_only(self):
        self.assertEqual(self.api.post('/api/admin/sportsbook/feed/sync/', {'job': 'rm -rf'}, format='json').status_code, 400)
        with patch('config.celery.app.send_task') as send:
            send.return_value.id = 'task-1'
            res = self.api.post('/api/admin/sportsbook/feed/sync/', {'job': 'sync_odds'}, format='json')
        self.assertEqual(res.status_code, 202)
        send.assert_called_once_with('apps.sportsbook.tasks.sync_fixture_odds')


class LeagueTests(AdminApiBase):
    def test_crud_bulk_and_guarded_delete(self):
        res = self.api.post('/api/admin/sportsbook/leagues/', {'name': 'Castle Lager PSL', 'country': 'Zimbabwe', 'sort_order': 5}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        league = LeagueSetting.objects.get(pk=res.json()['id'])
        self.assertEqual((league.provider, league.league_id > 900000), ('manual', True))
        other = LeagueSetting.objects.create(provider='api-football', league_id=39, name='Premier League', country='England')
        self.assertEqual(self.api.post('/api/admin/sportsbook/leagues/bulk/', {'ids': [league.id, other.id], 'enabled': False}, format='json').json(), {'updated': 2})
        self.assertEqual(self.api.get('/api/admin/sportsbook/leagues/?enabled=false').json()['count'], 2)
        self.assertEqual(self.api.get('/api/admin/sportsbook/leagues/?search=zimb').json()['results'][0]['name'], 'Castle Lager PSL')
        Event.objects.create(name='A vs B', league=other, starts_at=timezone.now() + timedelta(days=1))
        self.assertEqual(self.api.delete(f'/api/admin/sportsbook/leagues/{other.id}/').status_code, 409)
        self.assertEqual(self.api.delete(f'/api/admin/sportsbook/leagues/{league.id}/').status_code, 204)


class AdminEventTests(AdminApiBase):
    def test_create_edit_filter_and_delete_guard(self):
        kickoff = (timezone.now() + timedelta(days=1)).isoformat()
        res = self.api.post('/api/admin/sportsbook/events/', {
            'home_team_name': 'Dynamos', 'away_team_name': 'CAPS United', 'starts_at': kickoff,
            'odds': '2.10', 'odds_draw': '3.20', 'odds_away': '3.40',
        }, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        body = res.json()
        self.assertEqual((body['name'], body['source'], body['state'], body['home_team']['name']),
                         ('Dynamos vs CAPS United', 'manual', 'upcoming', 'Dynamos'))
        eid = body['id']
        res = self.api.patch(f'/api/admin/sportsbook/events/{eid}/', {'odds': '1.90', 'featured': True}, format='json')
        self.assertEqual((res.json()['odds'], res.json()['previous_odds'], res.json()['featured']), ('1.90', '2.10', True))
        self.assertEqual(self.api.patch(f'/api/admin/sportsbook/events/{eid}/', {'odds_away': '0.5'}, format='json').status_code, 400)
        self.assertEqual(self.api.get('/api/admin/sportsbook/events/?state=upcoming&q=caps').json()['count'], 1)
        self.assertEqual(self.api.get('/api/admin/sportsbook/events/?state=live').json()['count'], 0)
        self.assertEqual(self.api.get('/api/admin/sportsbook/events/summary/').json()['upcoming'], 1)
        Bet.objects.create(event='x', event_ref_id=eid, stake=D('1'), odds=D('1.9'))
        self.assertEqual(self.api.delete(f'/api/admin/sportsbook/events/{eid}/').status_code, 409)

    def test_locked_prices_survive_the_feed(self):
        ev = Event.objects.create(name='A vs B', provider=ApiFootballClient.provider_name, external_id='77',
                                  starts_at=timezone.now() + timedelta(days=1), odds=D('2.00'), odds_draw=D('3.00'), odds_away=D('4.00'))
        self.api.patch(f'/api/admin/sportsbook/events/{ev.id}/', {'odds': '2.50', 'prices_locked': True}, format='json')
        snap = OddsSnapshot(external_id='77', odds_home=D('1.50'), odds_draw=D('3.50'), odds_away=D('6.00'))
        self.assertIsNone(sb.sync_fixture_odds(snap))
        ev.refresh_from_db()
        self.assertEqual(ev.odds, D('2.50'))
        self.api.patch(f'/api/admin/sportsbook/events/{ev.id}/', {'prices_locked': False}, format='json')
        sb.sync_fixture_odds(snap)
        ev.refresh_from_db()
        self.assertEqual(ev.odds, D('1.50'))


class OverviewStatsTests(AdminApiBase):
    def test_shape(self):
        body = self.api.get('/api/admin/stats/').json()
        for key in ('today', 'queues', 'sportsbook', 'week', 'players', 'open_bets'):
            self.assertIn(key, body)
        self.assertEqual(len(body['week']), 7)
