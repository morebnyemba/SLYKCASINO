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
        self.assertEqual(set(self.polled()), {
            'Late 2nd half, no bets', 'Frozen with a bet', 'FT with an open bet (stats pending)'})
        self.assertEqual(self.polled()[-1], 'Late 2nd half, no bets')  # matches with bets first

    @override_settings(SPORTSBOOK_RESULT_POLL_MAX_MATCHES=2)
    def test_cap_per_run_and_rotation(self):
        for i in range(5):
            self.match(f'M{i}', 120 + i)
        asked = []
        with mock.patch(FETCH, side_effect=lambda ids: asked.append(sorted(ids)) or []):
            for _ in range(3):
                services.settle_finished_fixtures()
        self.assertEqual([len(a) for a in asked], [2, 2, 2])
        # Three runs of two cover all five before anything is asked twice.
        self.assertEqual(len({x for a in asked[:2] for x in a} | set(asked[2][:1])), 5)

    def test_check_result_now(self):
        ev = self.match('Frozen with a bet', 300, bet=True)
        api = APIClient()
        api.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))
        from apps.sportsbook.clients import ApiFootballClient
        fixture = ApiFootballClient.__new__(ApiFootballClient)._normalize({
            'fixture': {'id': 'Frozen with a bet', 'status': {'short': 'FT', 'elapsed': 90}, 'date': ev.starts_at.isoformat()},
            'teams': {'home': {'id': 1, 'name': 'A'}, 'away': {'id': 2, 'name': 'B'}},
            'goals': {'home': 2, 'away': 0}, 'score': {'halftime': {'home': 1, 'away': 0}, 'fulltime': {'home': 2, 'away': 0}},
            'league': {'id': 39, 'name': 'L'},
        })
        with mock.patch(FETCH, return_value=[fixture]) as fetch:
            body = api.post(f'/api/admin/sportsbook/events/{ev.id}/check-result/').json()
        fetch.assert_called_once_with(['Frozen with a bet'])
        self.assertEqual((body['found'], body['match']['status'], body['match']['score_home']), (True, 'FT', 2))
        self.assertEqual(Bet.objects.get(event_ref=ev).status, 'won')

        with mock.patch(FETCH, return_value=[]):
            self.assertFalse(api.post(f'/api/admin/sportsbook/events/{ev.id}/check-result/').json()['found'])
        manual = self.match('By hand', 300, provider='')
        self.assertEqual(api.post(f'/api/admin/sportsbook/events/{manual.id}/check-result/').status_code, 400)
