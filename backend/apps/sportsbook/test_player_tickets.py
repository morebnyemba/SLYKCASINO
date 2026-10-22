"""Ticket codes, the public "check a ticket" lookup and the player's paged ticket list."""
import secrets
from datetime import timedelta
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from apps.sportsbook import ticket_codes
from apps.sportsbook.models import Bet, BetLeg, BetSlip, Event, Team

PASSWORD = secrets.token_urlsafe(16)


class TicketTests(TestCase):
    def setUp(self):
        self.player = accounts.register_player(username='punter', email='p@example.com', password=PASSWORD)
        self.other = accounts.register_player(username='other', email='o@example.com', password=PASSWORD)
        home, away = Team.objects.create(name='Highlanders'), Team.objects.create(name='FC Platinum')
        self.live = Event.objects.create(name='Highlanders v FC Platinum', odds=D('2'), home_team=home, away_team=away,
                                         status='2H', elapsed=67, score_home=1, score_away=0,
                                         starts_at=timezone.now() - timedelta(minutes=80))
        self.done = Event.objects.create(name='A v B', odds=D('2'), status='FT', starts_at=timezone.now() - timedelta(days=1))
        mk = lambda **kw: Bet.objects.create(player_id=self.player.id, stake=D('10'), odds=D('2'), **kw)  # noqa: E731
        self.single_live = mk(event='live', event_ref=self.live, selection='home')
        self.single_won = mk(event='won', event_ref=self.done, status='won', payout=D('20'))
        self.single_lost = mk(event='lost', event_ref=self.done, status='lost')
        self.slip = BetSlip.objects.create(player_id=self.player.id, stake=D('5'), combined_odds=D('4'))
        BetLeg.objects.create(slip=self.slip, event='leg', event_ref=self.live, odds=D('2'))
        BetLeg.objects.create(slip=self.slip, event='leg2', event_ref=self.done, odds=D('2'), result='won')
        Bet.objects.create(player_id=self.other.id, stake=D('1'), odds=D('2'), event='not mine')
        self.api = APIClient()
        self.api.force_authenticate(self.player.user)

    def test_every_ticket_gets_a_unique_unguessable_code(self):
        codes = list(Bet.objects.values_list('code', flat=True)) + list(BetSlip.objects.values_list('code', flat=True))
        self.assertEqual(len(codes), len(set(codes)))
        for c in codes:
            self.assertEqual(len(c), ticket_codes.LENGTH)
            self.assertTrue(set(c) <= set(ticket_codes.ALPHABET))
        self.assertEqual(ticket_codes.normalise(' rmwq-umy7 f3 '), 'RMWQUMY7F3')

    def test_public_lookup_by_code_hides_the_player(self):
        anon = APIClient()
        code = self.slip.code
        body = anon.get(f'/api/tickets/{code.lower()[:5]}-{code.lower()[5:]}/').json()  # typed with a dash, lower case
        self.assertEqual((body['ticket'], body['kind'], body['mine'], len(body['legs'])), (f'M{self.slip.id}', 'multiple', False, 2))
        self.assertNotIn('player_id', body)
        self.assertNotIn('username', body)
        self.assertIsNone(body['cashout'])
        live_leg = next(leg for leg in body['legs'] if leg['match']['status'] == '2H')
        self.assertEqual((live_leg['match']['home'], live_leg['match']['away'], live_leg['match']['elapsed']), ('Highlanders', 'FC Platinum', 67))
        self.assertTrue(self.api.get(f'/api/tickets/{code}/').json()['mine'])
        self.assertEqual(anon.get('/api/tickets/ABCDEFGHJK/').status_code, 404)
        self.assertEqual(anon.get('/api/tickets/S12/').status_code, 400)  # ticket numbers don't work: they're guessable

    def test_my_tickets_tabs_counts_stats_and_paging(self):
        body = self.api.get('/api/my-tickets/').json()
        self.assertEqual(body['counts'], {'all': 4, 'open': 2, 'live': 2, 'settled': 2})
        self.assertEqual(body['stats'], {'staked': '35.00', 'returned': '20.00', 'net': '-15.00', 'won': 1, 'decided': 2})
        self.assertEqual({r['ticket'] for r in self.api.get('/api/my-tickets/', {'tab': 'live'}).json()['results']},
                         {f'S{self.single_live.id}', f'M{self.slip.id}'})
        self.assertEqual({r['ticket'] for r in self.api.get('/api/my-tickets/', {'tab': 'settled'}).json()['results']},
                         {f'S{self.single_won.id}', f'S{self.single_lost.id}'})
        seen, cursor = [], None
        while True:
            page = self.api.get('/api/my-tickets/', {'limit': 1, **({'cursor': cursor} if cursor else {})}).json()
            seen += [r['ticket'] for r in page['results']]
            cursor = page['next_cursor']
            if not cursor:
                break
        self.assertEqual(len(seen), 4)
        self.assertEqual(len(set(seen)), 4)
        self.assertIn(APIClient().get('/api/my-tickets/').status_code, (401, 403))

    def test_staff_can_find_a_ticket_by_its_code(self):
        staff = APIClient()
        staff.force_authenticate(User.objects.create_user('ops', 'ops@example.com', 'x', is_staff=True))
        res = staff.get('/api/admin/tickets/', {'q': self.single_won.code}).json()['results']
        self.assertEqual([r['ticket'] for r in res], [f'S{self.single_won.id}'])
