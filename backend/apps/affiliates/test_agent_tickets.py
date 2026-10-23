"""The agent dashboard's ticket numbers and the agent's view of their players' tickets."""
import secrets
from datetime import timedelta
from decimal import Decimal as D

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from apps.affiliates import services
from apps.affiliates.models import Affiliate, Commission
from apps.sportsbook.models import Bet, BetLeg, BetSlip, Event

PASSWORD = secrets.token_urlsafe(16)


class AgentTicketTests(TestCase):
    def setUp(self):
        self.agent = accounts.register_player(username='agent', email='a@example.com', password=PASSWORD)
        self.affiliate = services.apply(player_id=self.agent.id, code='AGENT')
        services.set_status(self.affiliate.id, Affiliate.Status.ACTIVE)
        self.customer = accounts.register_player(username='customer', email='c@example.com', password=PASSWORD)
        stranger = accounts.register_player(username='stranger', email='s@example.com', password=PASSWORD)
        services.attach_referral(player_id=self.customer.id, code='AGENT')
        event = Event.objects.create(name='A v B', odds=D('2'), starts_at=timezone.now())
        mk = lambda player, **kw: Bet.objects.create(player_id=player.id, stake=D('10'), odds=D('2'), event='x',  # noqa: E731
                                                     event_ref=event, **kw)
        self.open = mk(self.customer)
        self.won = mk(self.customer, status='won', payout=D('20'))
        self.lost = mk(self.customer, status='lost')
        yesterday = mk(self.customer, status='lost')
        Bet.objects.filter(pk=yesterday.pk).update(placed_at=timezone.now() - timedelta(days=1))
        mk(self.customer, status='rejected')
        self.slip = BetSlip.objects.create(player_id=self.customer.id, stake=D('5'), combined_odds=D('4'))
        BetLeg.objects.create(slip=self.slip, event='leg', event_ref=event, odds=D('2'))
        mk(stranger, status='won')
        self.api = APIClient()
        self.api.force_authenticate(self.agent.user)

    def test_dashboard_counts_todays_tickets(self):
        stats = self.api.get('/api/affiliates/me/').json()['stats']
        self.assertEqual(stats['tickets_today'], {'played': 4, 'won': 1, 'lost': 1, 'open': 2})

    def test_agent_sees_only_their_players_tickets_masked(self):
        body = self.api.get('/api/affiliates/me/tickets/').json()
        self.assertEqual(len(body['results']), 5)  # every day, never the rejected one or the stranger's
        self.assertEqual(body['counts'], {'open': 2, 'won': 1, 'lost': 2, 'void': 0})
        row = body['results'][0]
        self.assertEqual((row['customer'], row['code']), ('cu*****', ''))
        self.assertNotIn('player_id', row)
        won = self.api.get('/api/affiliates/me/tickets/', {'status': 'won'}).json()['results']
        self.assertEqual([r['ticket'] for r in won], [f'S{self.won.id}'])
        first = self.api.get('/api/affiliates/me/tickets/', {'limit': 2}).json()
        rest = self.api.get('/api/affiliates/me/tickets/', {'limit': 10, 'cursor': first['next_cursor']}).json()
        self.assertEqual(len(first['results']) + len(rest['results']), 5)
        self.assertIsNone(rest['next_cursor'])

    def test_players_and_strangers_cannot_look(self):
        api = APIClient()
        api.force_authenticate(self.customer.user)
        self.assertEqual(api.get('/api/affiliates/me/tickets/').status_code, 404)
        self.assertEqual(APIClient().get('/api/affiliates/me/tickets/').status_code, 401)


class LosingTicketCommissionTests(TestCase):
    """30% of the stake on every ticket a referred player loses, per day."""

    def setUp(self):
        self.agent = accounts.register_player(username='agent', email='a@example.com', password=PASSWORD)
        self.affiliate = services.apply(player_id=self.agent.id, code='AGENT')
        services.set_status(self.affiliate.id, Affiliate.Status.ACTIVE)
        self.affiliate.refresh_from_db()
        self.customer = accounts.register_player(username='customer', email='c@example.com', password=PASSWORD)
        self.stranger = accounts.register_player(username='stranger', email='s@example.com', password=PASSWORD)
        services.attach_referral(player_id=self.customer.id, code='AGENT')
        self.yesterday = timezone.localdate() - timedelta(days=1)
        settled = timezone.make_aware(timezone.datetime.combine(self.yesterday, timezone.datetime.min.time())) + timedelta(hours=20)
        event = Event.objects.create(name='A v B', odds=D('2'), starts_at=timezone.now())
        for player, stake, state in ((self.customer, '10', 'lost'), (self.customer, '20', 'lost'),
                                     (self.customer, '50', 'won'), (self.customer, '7', 'void'), (self.stranger, '100', 'lost')):
            Bet.objects.create(player_id=player.id, stake=D(stake), odds=D('2'), event='x', event_ref=event,
                               status=state, settled_at=settled)
        BetSlip.objects.create(player_id=self.customer.id, stake=D('5'), combined_odds=D('4'), status='lost', settled_at=settled)
        Bet.objects.create(player_id=self.customer.id, stake=D('40'), odds=D('2'), event='x', event_ref=event,
                           status='lost', settled_at=timezone.now())

    def test_new_agents_get_thirty_percent(self):
        self.assertEqual(self.affiliate.revshare_percent, D('30'))

    def test_a_closed_day_pays_once(self):
        c = services.compute_stake_commission(self.affiliate, self.yesterday)
        # 10 + 20 + 5 lost (the win, the void and the stranger's ticket don't count) × 30%
        self.assertEqual((c.kind, c.base_amount, c.amount, c.period), (Commission.Kind.STAKE, D('35'), D('10.50'), self.yesterday))
        self.assertEqual(c.note, '3 losing tickets')
        self.assertEqual(services.compute_stake_commission(self.affiliate, self.yesterday).pk, c.pk)
        self.assertIsNone(services.compute_stake_commission(self.affiliate, timezone.localdate()))  # not over yet
        result = services.run_commissions()
        self.assertEqual(result['stake'], 1)
        self.assertEqual(Commission.objects.filter(kind='stake').count(), 1)

    def test_dashboard_shows_today_so_far_and_the_month(self):
        services.compute_stake_commission(self.affiliate, self.yesterday)
        stats = services.dashboard(self.affiliate)
        self.assertEqual((stats['lost_stakes_today'], stats['losing_tickets_today'], stats['commission_today']),
                         (D('40'), 1, D('12.00')))
        self.assertEqual(stats['commission_total'], D('22.50'))
        if self.yesterday.month == timezone.localdate().month:
            self.assertEqual(stats['commission_month'], D('22.50'))
