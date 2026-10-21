"""Match housekeeping: services.clear_old_matches and the listing's stale-live cut-off."""
from datetime import timedelta
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.core.management import call_command
from unittest import mock

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.sportsbook import services
from apps.sportsbook.models import Bet, BetLeg, BetSlip, Event, Market, MarketOutcome


@override_settings(SPORTSBOOK_MATCH_MAX_MINUTES=180, SPORTSBOOK_DELETE_MATCHES_AFTER_HOURS=48)
class ClearOldMatchesTests(TestCase):
    def match(self, name, hours_ago, **kw):
        return Event.objects.create(name=name, odds=D('2'), starts_at=timezone.now() - timedelta(hours=hours_ago), **kw)

    def test_closes_stale_deletes_untouched_keeps_ticketed(self):
        upcoming = self.match('Upcoming', -5)
        recent = self.match('Just finished', 2, status='FT')
        stale = self.match('Feed went quiet', 10, status='2H')
        old_empty = self.match('Old, no bets', 72, status='FT')
        Market.objects.create(event=old_empty, key='ou25', name='Over/Under 2.5')
        old_single = self.match('Old single', 72, status='FT')
        Bet.objects.create(player_id=1, event='x', event_ref=old_single, stake=D('1'), odds=D('2'), status='won')
        old_leg = self.match('Old leg', 72, status='CANC')
        slip = BetSlip.objects.create(player_id=1, stake=D('1'), combined_odds=D('2'))
        BetLeg.objects.create(slip=slip, event='y', event_ref=old_leg, odds=D('2'))
        old_outcome = self.match('Old market bet', 72, status='FT')
        out = MarketOutcome.objects.create(market=Market.objects.create(event=old_outcome, key='btts', name='BTTS'),
                                           key='yes', label='Yes', odds=D('1.8'))
        Bet.objects.create(player_id=1, event='z', outcome_ref=out, stake=D('1'), odds=D('1.8'))

        preview = services.clear_old_matches(dry_run=True)
        self.assertEqual(preview, {'closed': 5, 'deleted': 1, 'kept_with_tickets': 3})
        self.assertTrue(Event.objects.filter(pk=old_empty.pk).exists())  # a dry run changes nothing

        self.assertEqual(services.clear_old_matches(), preview)
        self.assertFalse(Event.objects.filter(pk=old_empty.pk).exists())
        self.assertFalse(Market.objects.filter(key='ou25').exists())
        self.assertEqual(Event.objects.get(pk=stale.pk).status, 'NR')
        left = {e.name: e.is_open for e in Event.objects.all()}
        self.assertEqual(left, {'Upcoming': True, 'Just finished': True, 'Feed went quiet': False,
                                'Old single': False, 'Old leg': False, 'Old market bet': False})
        self.assertEqual(Bet.objects.get(event='x').event_ref_id, old_single.pk)
        self.assertEqual(services.clear_old_matches(), {'closed': 0, 'deleted': 0, 'kept_with_tickets': 3})
        del upcoming, recent, stale

    def test_frozen_live_match_drops_off_the_board(self):
        self.match('Live now', 1, status='2H')
        self.match('Frozen live', 10, status='2H', is_open=False)
        self.assertEqual({e.name for e in services.list_events(upcoming=True)}, {'Live now'})

    @override_settings(SPORTSBOOK_DELETE_MATCHES_AFTER_HOURS=0)
    def test_zero_turns_deleting_off(self):
        self.match('Old', 100)
        self.assertEqual(services.clear_old_matches(), {'closed': 1, 'deleted': 0, 'kept_with_tickets': 0})
        self.assertEqual(Event.objects.count(), 1)

    def test_admin_button_and_command(self):
        self.match('Old, no bets', 72)
        api = APIClient()
        api.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))
        self.assertEqual(api.post('/api/admin/sportsbook/events/cleanup/', {'dry_run': True}, format='json').json()['deleted'], 1)
        self.assertEqual(Event.objects.count(), 1)
        # The real run is queued on the worker; run it inline here.
        with mock.patch('apps.sportsbook.tasks.clear_old_matches.delay', side_effect=lambda: services.clear_old_matches()) as queued:
            res = api.post('/api/admin/sportsbook/events/cleanup/', {}, format='json')
        self.assertEqual((res.status_code, res.json()['deleted'], res.json()['queued']), (202, 1, True))
        queued.assert_called_once()
        self.assertEqual(Event.objects.count(), 0)
        self.assertIn(APIClient().post('/api/admin/sportsbook/events/cleanup/').status_code, (401, 403))
        self.match('Another', 72)
        call_command('clear_old_matches', '--dry-run', stdout=open('/dev/null', 'w'))
        self.assertEqual(Event.objects.count(), 1)

    def test_bulk_delete_in_batches_leaves_ticketed_markets_alone(self):
        def with_markets(name, hours_ago, n=30):
            ev = self.match(name, hours_ago, status='FT')
            for i in range(n):
                m = Market.objects.create(event=ev, key=f'm{i}', name=f'Market {i}')
                for k in ('a', 'b', 'c'):
                    MarketOutcome.objects.create(market=m, key=k, label=k, odds=D('2'))
            return ev
        for i in range(5):
            with_markets(f'Old {i}', 72)
        keep = with_markets('Old with a bet', 72, n=2)
        out = MarketOutcome.objects.filter(market__event=keep).first()
        Bet.objects.create(player_id=1, event='k', outcome_ref=out, stake=D('1'), odds=D('2'))
        fresh = with_markets('Recent', 1, n=2)

        old = Event.objects.filter(starts_at__lte=timezone.now() - timedelta(hours=48)).exclude(pk=keep.pk)
        self.assertEqual(services._delete_untouched_matches(old, batch=2), 5)
        self.assertEqual(set(Event.objects.values_list('name', flat=True)), {'Old with a bet', 'Recent'})
        self.assertEqual(Market.objects.count(), 4)
        self.assertEqual(MarketOutcome.objects.count(), 12)
        self.assertEqual(Bet.objects.get(event='k').outcome_ref_id, out.pk)
        del fresh


@override_settings(SPORTSBOOK_MATCH_MAX_MINUTES=180)
class StuckLiveTests(TestCase):
    def setUp(self):
        mk = lambda name, h, status: Event.objects.create(  # noqa: E731
            name=name, odds=D('2'), starts_at=timezone.now() - timedelta(hours=h), status=status)
        mk('Live now', 1, '2H')
        mk('Frozen live', 30, '2H')
        mk('Never updated', 30, 'NS')
        mk('Finished', 30, 'FT')
        mk('Upcoming', -2, '')
        self.api = APIClient()
        self.api.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))

    def names(self, state):
        return {m['name'] for m in self.api.get('/api/admin/sportsbook/events/', {'state': state}).json()['results']}

    def test_old_live_matches_are_not_live_but_no_result(self):
        self.assertEqual(self.names('live'), {'Live now'})
        self.assertEqual(self.names('stuck'), {'Frozen live', 'Never updated'})
        summary = self.api.get('/api/admin/sportsbook/events/summary/').json()
        self.assertEqual((summary['live'], summary['stuck']), (1, 2))
        states = {m['name']: m['state'] for m in self.api.get('/api/admin/sportsbook/events/', {'state': 'all'}).json()['results']}
        self.assertEqual(states['Frozen live'], 'stuck')
        self.assertEqual(states['Live now'], 'live')
        stats = self.api.get('/api/admin/stats/').json()
        self.assertEqual(stats['sportsbook']['live'], 1)


@override_settings(SPORTSBOOK_MATCH_MAX_MINUTES=180)
class EndStaleLiveTests(TestCase):
    def test_frozen_live_match_ends_without_a_result(self):
        mk = lambda name, minutes, status: Event.objects.create(  # noqa: E731
            name=name, odds=D('2'), starts_at=timezone.now() - timedelta(minutes=minutes), status=status,
            score_home=1, score_away=0, provider='api-football', external_id=name)
        playing = mk('Extra time', 150, 'ET')
        frozen = mk('Frozen', 200, '2H')
        bet = Bet.objects.create(player_id=1, event='Frozen', event_ref=frozen, selection='home', stake=D('5'), odds=D('2'))

        # The result poll asks the feed first; it has nothing new for either match.
        with mock.patch('apps.sportsbook.services.ApiFootballClient.fetch_fixtures_by_ids', return_value=[]) as fetch:
            services.settle_finished_fixtures()
        fetch.assert_called_once()

        playing.refresh_from_db(); frozen.refresh_from_db(); bet.refresh_from_db()
        self.assertEqual(playing.status, 'ET')                       # still inside the 3 hours
        self.assertEqual((frozen.status, frozen.is_open), ('NR', False))
        self.assertEqual((frozen.score_home, frozen.score_away), (1, 0))  # kept as last seen
        self.assertEqual(bet.status, 'open')                          # NOT settled from 1-0
        self.assertFalse(Event.objects.filter(services.live_now()).filter(pk=frozen.pk).exists())
        self.assertTrue(Event.objects.filter(services.stuck_without_result()).filter(pk=frozen.pk).exists())
        # Still polled for a late result.
        self.assertIn(frozen.pk, list(services.events_awaiting_settlement().values_list('pk', flat=True)))
