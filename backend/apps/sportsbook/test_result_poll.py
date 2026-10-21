"""The result poll: what it asks the provider about, the per-run cap and rotation,
and the admin's "Check result now"."""
from datetime import timedelta
from decimal import Decimal as D
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.sportsbook import services
from apps.sportsbook.models import Bet, Event

FETCH = 'apps.sportsbook.services.ApiFootballClient.fetch_fixtures_by_ids'


@override_settings(SPORTSBOOK_MATCH_MAX_MINUTES=180)
class ResultPollTests(TestCase):
    def setUp(self):
        from apps.accounts import services as accounts
        self.player = accounts.create_player(username='punter')

    def match(self, name, minutes_ago, status='2H', bet=False, provider='api-football'):
        ev = Event.objects.create(name=name, odds=D('2'), status=status, provider=provider, external_id=name,
                                  starts_at=timezone.now() - timedelta(minutes=minutes_ago))
        if bet:
            Bet.objects.create(player_id=self.player.id, event=name, event_ref=ev, selection='home', stake=D('1'), odds=D('2'))
        return ev

    def fixture(self, ev, status, home, away):
        from apps.sportsbook.clients import ApiFootballClient
        return ApiFootballClient.__new__(ApiFootballClient)._normalize({
            'fixture': {'id': ev.external_id, 'status': {'short': status, 'elapsed': 90}, 'date': ev.starts_at.isoformat()},
            'teams': {'home': {'id': 1, 'name': 'A'}, 'away': {'id': 2, 'name': 'B'}},
            'goals': {'home': home, 'away': away},
            'score': {'halftime': {'home': home, 'away': away}, 'fulltime': {'home': home, 'away': away}},
            'league': {'id': 39, 'name': 'L'},
        })

    def polled(self):
        return [e.name for e in services.events_awaiting_settlement()]

    def test_asks_only_about_matches_that_matter(self):
        self.match('Too early', 60)
        self.match('Late 2nd half, no bets', 110)
        self.match('Ended NR, no bets', 300, status='NR')
        self.match('Frozen, no bets, past 3h', 300)
        self.match('FT, no bets', 120, status='FT')
        self.match('Frozen with a bet', 300, bet=True)
        self.match('FT with an open bet (stats pending)', 300, status='FT', bet=True)
        self.match('Too old', 60 * 24 * 5, bet=True)
        # The general poll: open bets on matches that aren't marked live.
        self.assertEqual(set(self.polled()), {'FT with an open bet (stats pending)'})
        # The overdue-live check: everything still marked live 100'+ after kick-off (last 2 days).
        asked = []
        with mock.patch(FETCH, side_effect=lambda ids: asked.extend(ids) or []):
            report = services.check_overdue_live_matches()
        self.assertEqual(set(asked), {'Late 2nd half, no bets', 'Frozen, no bets, past 3h', 'Frozen with a bet'})
        self.assertEqual(report, {'checked': 3, 'answered': 0, 'still_live': 3, 'ended_no_result': 3})  # incl. 'Too old'

    def test_overdue_live_match_gets_its_full_time(self):
        ev = self.match('Morning match', 400, bet=True)
        with mock.patch(FETCH, return_value=[self.fixture(ev, 'FT', 2, 0)]):
            report = services.check_overdue_live_matches()
        ev.refresh_from_db()
        self.assertEqual((ev.status, ev.score_home, ev.score_away), ('FT', 2, 0))  # the real result, not NR
        self.assertEqual(Bet.objects.get(event_ref=ev).status, 'won')
        self.assertEqual(report, {'checked': 1, 'answered': 1, 'still_live': 0, 'ended_no_result': 0})

    @override_settings(SPORTSBOOK_RESULT_POLL_MAX_MATCHES=2)
    def test_cap_per_run_and_rotation(self):
        for i in range(5):
            self.match(f'M{i}', 120 + i)
        asked = []
        with mock.patch(FETCH, side_effect=lambda ids: asked.append(sorted(ids)) or []):
            for _ in range(3):
                services.check_overdue_live_matches()
        self.assertEqual([len(a) for a in asked], [2, 2, 2])
        # Three runs of two cover all five before anything is asked twice.
        self.assertEqual(len({x for a in asked[:2] for x in a} | set(asked[2][:1])), 5)

    def test_check_result_now(self):
        ev = self.match('Frozen with a bet', 300, bet=True)
        api = APIClient()
        api.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))
        with mock.patch(FETCH, return_value=[self.fixture(ev, 'FT', 2, 0)]) as fetch:
            body = api.post(f'/api/admin/sportsbook/events/{ev.id}/check-result/').json()
        fetch.assert_called_once_with(['Frozen with a bet'])
        self.assertEqual((body['found'], body['match']['status'], body['match']['score_home']), (True, 'FT', 2))
        self.assertEqual(Bet.objects.get(event_ref=ev).status, 'won')

        with mock.patch(FETCH, return_value=[]):
            self.assertFalse(api.post(f'/api/admin/sportsbook/events/{ev.id}/check-result/').json()['found'])
        manual = self.match('By hand', 300, provider='')
        self.assertEqual(api.post(f'/api/admin/sportsbook/events/{manual.id}/check-result/').status_code, 400)


class LiveScoresPollTests(TestCase):
    def test_polls_only_while_something_could_be_live(self):
        with mock.patch('apps.sportsbook.services.ApiFootballClient.fetch_fixtures', return_value=[]) as fetch:
            Event.objects.create(name='Tomorrow', odds=D('2'), provider='api-football', external_id='1',
                                 starts_at=timezone.now() + timedelta(days=1))
            Event.objects.create(name='Done', odds=D('2'), provider='api-football', external_id='2', status='FT',
                                 starts_at=timezone.now() - timedelta(minutes=100))
            self.assertEqual(services.sync_live_fixtures(), 0)
            fetch.assert_not_called()  # quiet: no API call

            Event.objects.create(name='Kicked off', odds=D('2'), provider='api-football', external_id='3',
                                 starts_at=timezone.now() - timedelta(minutes=30))
            services.sync_live_fixtures()
            fetch.assert_called_once_with(date=None, live='all')

    def test_beat_runs_it_every_15_seconds(self):
        from django.conf import settings
        entry = settings.CELERY_BEAT_SCHEDULE['sportsbook-sync-live-fixtures']
        self.assertEqual((entry['schedule'], entry['options']['expires']), (15.0, 15.0))
