"""Leagues: parsed from fixtures, linked to events (incl. backfill), featured
competitions ordered first, and exposed on the events API."""
from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.sportsbook import services as sb
from apps.sportsbook.clients import ApiFootballClient, FixtureLeague, FixtureUpdate
from apps.sportsbook.models import Event, LeagueSetting

EPL = FixtureLeague(external_id=39, name='Premier League', country='England',
                    logo_url='https://media.example/leagues/39.png', flag_url='https://media.example/flags/gb.svg')
OBSCURE = FixtureLeague(external_id=9999, name='Regional League', country='Somewhere')


def _fixture(fid, league, status='NS'):
    return FixtureUpdate(external_id=str(fid), name=f'Home {fid} vs Away {fid}', status=status,
                         starts_at=timezone.now() + timedelta(days=1), goals_home=None, goals_away=None,
                         league=league)


class LeagueParsingTests(TestCase):
    def test_fixture_payload_carries_its_league(self):
        raw = {
            'fixture': {'id': 1, 'status': {'short': 'NS'}},
            'league': {'id': 39, 'name': 'Premier League', 'country': 'England', 'logo': 'l.png', 'flag': 'f.svg'},
            'teams': {'home': {'id': 1, 'name': 'A'}, 'away': {'id': 2, 'name': 'B'}},
            'goals': {},
        }
        league = ApiFootballClient()._normalize(raw).league
        self.assertEqual((league.external_id, league.name, league.country, league.flag_url), (39, 'Premier League', 'England', 'f.svg'))


class LeagueLinkTests(TestCase):
    def test_import_links_league_and_orders_featured_first(self):
        epl_event = sb._create_event_from_fixture(_fixture(1, EPL))
        other_event = sb._create_event_from_fixture(_fixture(2, OBSCURE))
        self.assertEqual(epl_event.league.name, 'Premier League')
        epl, other = LeagueSetting.objects.get(league_id=39), LeagueSetting.objects.get(league_id=9999)
        self.assertLess(epl.sort_order, other.sort_order)
        self.assertEqual(other_event.league, other)

    def test_existing_events_are_backfilled_and_details_refreshed(self):
        event = Event.objects.create(name='Old', provider='api-football', external_id='7')
        sb._create_event_from_fixture(_fixture(7, EPL))
        event.refresh_from_db()
        self.assertEqual(event.league.league_id, 39)
        renamed = FixtureLeague(external_id=39, name='Premier League 2026', country='England')
        sb.sync_fixture(_fixture(7, renamed))
        self.assertEqual(LeagueSetting.objects.get(league_id=39).name, 'Premier League 2026')

    def test_events_api_exposes_league(self):
        sb._create_event_from_fixture(_fixture(3, EPL))
        Event.objects.filter(external_id='3').update(has_odds=True)
        rows = APIClient().get('/api/events/?upcoming=true').json()['results']
        self.assertEqual(rows[0]['league']['name'], 'Premier League')
        self.assertEqual(rows[0]['league']['country'], 'England')
