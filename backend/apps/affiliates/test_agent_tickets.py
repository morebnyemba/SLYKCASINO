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

    def test_staff_viewing_as_the_agent_see_full_names(self):
        from django.contrib.auth.models import User
        from rest_framework_simplejwt.tokens import RefreshToken

        from apps.accounts import impersonation

        staff = User.objects.create_user('ops', 'ops@example.com', PASSWORD, is_staff=True)
        session = impersonation.start(staff, self.agent, mode='view')
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken(session["refresh"]).access_token}')
        self.assertEqual(api.get('/api/affiliates/me/tickets/').json()['results'][0]['customer'], 'customer')
        self.assertEqual(api.get('/api/affiliates/me/').json()['stats']['referrals'][0]['player'], 'customer')
        self.assertEqual(self.api.get('/api/affiliates/me/').json()['stats']['referrals'][0]['player'], 'cu*****')

    def test_players_and_strangers_cannot_look(self):
        api = APIClient()
        api.force_authenticate(self.customer.user)
        self.assertEqual(api.get('/api/affiliates/me/tickets/').status_code, 404)
        self.assertEqual(APIClient().get('/api/affiliates/me/tickets/').status_code, 401)


class LosingTicketCommissionTests(TestCase):
    """30% of the stake on every ticket a referred player loses, credited
    automatically 3 minutes after it settles."""

    def setUp(self):
        self.agent = accounts.register_player(username='agent', email='a@example.com', password=PASSWORD)
        self.affiliate = services.apply(player_id=self.agent.id, code='AGENT')
        services.set_status(self.affiliate.id, Affiliate.Status.ACTIVE)
        self.affiliate.refresh_from_db()
        self.customer = accounts.register_player(username='customer', email='c@example.com', password=PASSWORD)
        stranger = accounts.register_player(username='stranger', email='s@example.com', password=PASSWORD)
        services.attach_referral(player_id=self.customer.id, code='AGENT')
        now = timezone.now()
        self.event = Event.objects.create(name='A v B', odds=D('2'), starts_at=now)
        ago = lambda minutes: now - timedelta(minutes=minutes)  # noqa: E731
        mk = lambda player, stake, state, settled: Bet.objects.create(  # noqa: E731
            player_id=player.id, stake=D(stake), odds=D('2'), event='x', event_ref=self.event, status=state, settled_at=settled)
        self.lost = mk(self.customer, '10', 'lost', ago(5))
        self.fresh = mk(self.customer, '40', 'lost', ago(1))       # settled under 3 minutes ago
        mk(self.customer, '50', 'won', ago(5))
        mk(self.customer, '7', 'void', ago(5))
        mk(stranger, '100', 'lost', ago(5))                         # not referred
        mk(self.customer, '9', 'lost', now - timedelta(days=5))     # older than the catch-up window
        self.slip = BetSlip.objects.create(player_id=self.customer.id, stake=D('5'), combined_odds=D('4'),
                                           status='lost', settled_at=ago(4))

    def test_new_agents_get_thirty_percent(self):
        self.assertEqual(self.affiliate.revshare_percent, D('30'))

    def test_credited_automatically_once_three_minutes_after_settling(self):
        self.assertEqual(services.credit_losing_tickets(), 2)
        rows = {c.ticket: c for c in Commission.objects.filter(kind='stake')}
        self.assertEqual(set(rows), {f'S{self.lost.id}', f'M{self.slip.id}'})
        c = rows[f'S{self.lost.id}']
        self.assertEqual((c.base_amount, c.amount, c.status), (D('10'), D('3.00'), Commission.Status.APPROVED))
        self.assertEqual(services.balance(self.affiliate)['available'], D('4.50'))  # ready to withdraw, no approval
        self.assertEqual(services.credit_losing_tickets(), 0)  # never twice
        # Three minutes on, the fresh one is paid too.
        self.assertEqual(services.credit_losing_tickets(now=timezone.now() + timedelta(minutes=3)), 1)
        self.assertEqual(services.balance(self.affiliate)['available'], D('16.50'))

    def test_suspended_agents_are_not_credited(self):
        services.set_status(self.affiliate.id, Affiliate.Status.SUSPENDED)
        self.assertEqual(services.credit_losing_tickets(), 0)

    def test_dashboard_today_counts_credited_and_on_its_way(self):
        services.credit_losing_tickets()
        stats = services.dashboard(self.affiliate)
        # 10 + 40 + 5 lost today; 4.50 credited, 12.00 still inside the 3 minutes.
        self.assertEqual((stats['lost_stakes_today'], stats['losing_tickets_today']), (D('55'), 3))
        self.assertEqual((stats['commission_today'], stats['commission_total']), (D('16.50'), D('16.50')))


class AgentReportTests(TestCase):
    """Deposits, tickets, clicks and sign-ups for a chosen day or date range."""

    def setUp(self):
        from apps.wallet import services as wallet

        self.agent = accounts.register_player(username='agent', email='a@example.com', password=PASSWORD)
        self.affiliate = services.apply(player_id=self.agent.id, code='AGENT')
        services.set_status(self.affiliate.id, Affiliate.Status.ACTIVE)
        self.customer = accounts.register_player(username='customer', email='c@example.com', password=PASSWORD)
        stranger = accounts.register_player(username='stranger', email='s@example.com', password=PASSWORD)
        services.attach_referral(player_id=self.customer.id, code='AGENT')
        services.update_programme(welcome_bonus_percent=0)
        wallet.deposit(player_id=self.customer.id, amount=D('20'), idempotency_key='d1')
        wallet.deposit(player_id=self.customer.id, amount=D('15'), idempotency_key='d2')
        wallet.deposit(player_id=stranger.id, amount=D('99'), idempotency_key='d3')
        old = wallet.deposit(player_id=self.customer.id, amount=D('7'), idempotency_key='d4')
        from apps.wallet.models import LedgerEntry
        LedgerEntry.objects.filter(idempotency_key='d4').update(created_at=timezone.now() - timedelta(days=400))
        del old
        services.record_click('AGENT')
        self.api = APIClient()
        self.api.force_authenticate(self.agent.user)

    def test_today(self):
        body = self.api.get('/api/affiliates/me/report/').json()
        self.assertEqual((body['frame'], body['clicks'], body['signups']), ('today', 1, 1))
        d = body['deposits']
        self.assertEqual((d['total'], d['count'], d['depositors'], d['more']), ('35.00', 2, 1, False))
        self.assertEqual([(i['customer'], i['amount']) for i in d['items']], [('cu*****', '15.00'), ('cu*****', '20.00')])

    def test_custom_range_up_to_ten_years(self):
        today = timezone.localdate()
        start = (today - timedelta(days=500)).isoformat()
        body = self.api.get('/api/affiliates/me/report/', {'frame': 'custom', 'start': start, 'end': today.isoformat()}).json()
        self.assertEqual((body['deposits']['total'], body['deposits']['count']), ('42.00', 3))
        self.assertEqual((body['start'], body['end']), (start, today.isoformat()))
        too_old = today.replace(year=today.year - 11, day=1).isoformat()
        r = self.api.get('/api/affiliates/me/report/', {'frame': 'custom', 'start': too_old, 'end': today.isoformat()})
        self.assertEqual(r.status_code, 400)
        self.assertEqual(self.api.get('/api/affiliates/me/report/', {'frame': 'all'}).status_code, 400)
