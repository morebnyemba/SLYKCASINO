"""Top Events: staff tick leagues in the admin; their matches show on the tab."""
from __future__ import annotations

import importlib
from datetime import timedelta
from decimal import Decimal

from django.apps import apps as django_apps
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.sportsbook.models import Event, LeagueSetting


class TopEventsTests(TestCase):
    def setUp(self):
        self.staff = APIClient()
        self.staff.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))
        self.psl = LeagueSetting.objects.create(league_id=288, name='Premier Soccer League', sort_order=160)
        self.zim = LeagueSetting.objects.create(league_id=401, name='Zimbabwe Premier League')
        Event.objects.create(name='Dynamos vs Highlanders', league=self.zim, starts_at=timezone.now() + timedelta(hours=3),
                             status='NS', odds=Decimal('2.00'), odds_draw=Decimal('3.20'), odds_away=Decimal('3.80'))

    def test_tick_a_league_in_the_admin_and_the_player_api_says_so(self):
        url = f'/api/admin/sportsbook/leagues/{self.zim.id}/'
        self.assertFalse(self.staff.get(url).json()['top_events'])
        self.assertTrue(self.staff.patch(url, {'top_events': True}, format='json').json()['top_events'])
        events = APIClient().get('/api/events/').json()
        rows = events['results'] if isinstance(events, dict) else events
        self.assertTrue(next(e for e in rows if e['name'] == 'Dynamos vs Highlanders')['league']['top_events'])

    def test_bulk_and_filter(self):
        res = self.staff.post('/api/admin/sportsbook/leagues/bulk/', {'ids': [self.psl.id, self.zim.id], 'top_events': True},
                              format='json')
        self.assertEqual(res.json()['updated'], 2)
        names = [r['name'] for r in self.staff.get('/api/admin/sportsbook/leagues/?top=true').json()['results']]
        self.assertEqual(sorted(names), ['Premier Soccer League', 'Zimbabwe Premier League'])
        self.staff.post('/api/admin/sportsbook/leagues/bulk/', {'ids': [self.psl.id], 'top_events': False}, format='json')
        names = [r['name'] for r in self.staff.get('/api/admin/sportsbook/leagues/?top=true').json()['results']]
        self.assertEqual(names, ['Zimbabwe Premier League'])
        self.assertEqual(self.staff.post('/api/admin/sportsbook/leagues/bulk/', {'ids': [self.psl.id]}, format='json').status_code, 400)

    def test_migration_keeps_todays_top_events(self):
        mig = importlib.import_module('apps.sportsbook.migrations.0035_league_top_events')
        mig.keep_todays_top_events(django_apps, None)
        self.psl.refresh_from_db()
        self.zim.refresh_from_db()
        self.assertEqual((self.psl.top_events, self.zim.top_events), (True, False))   # featured order < 1000 only
