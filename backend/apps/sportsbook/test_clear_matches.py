"""Match housekeeping: services.clear_old_matches and the listing's stale-live cut-off."""
from datetime import timedelta
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.sportsbook import services
from apps.sportsbook.models import Bet, BetLeg, BetSlip, Event, Market, MarketOutcome


@override_settings(SPORTSBOOK_STALE_MATCH_HOURS=6, SPORTSBOOK_DELETE_MATCHES_AFTER_HOURS=48)
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

    @override_settings(SPORTSBOOK_STALE_MATCH_HOURS=0, SPORTSBOOK_DELETE_MATCHES_AFTER_HOURS=0)
    def test_zero_turns_steps_off(self):
        self.match('Old', 100)
        self.assertEqual(services.clear_old_matches(), {'closed': 0, 'deleted': 0, 'kept_with_tickets': 0})

    def test_admin_button_and_command(self):
        self.match('Old, no bets', 72)
        api = APIClient()
        api.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))
        self.assertEqual(api.post('/api/admin/sportsbook/events/cleanup/', {'dry_run': True}, format='json').json()['deleted'], 1)
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(api.post('/api/admin/sportsbook/events/cleanup/', {}, format='json').json()['deleted'], 1)
        self.assertEqual(Event.objects.count(), 0)
        self.assertIn(APIClient().post('/api/admin/sportsbook/events/cleanup/').status_code, (401, 403))
        self.match('Another', 72)
        call_command('clear_old_matches', '--dry-run', stdout=open('/dev/null', 'w'))
        self.assertEqual(Event.objects.count(), 1)
