"""Why agents missed money on lost tickets, and the tools that recover it:
the hourly catch-up, staff linking a customer, and the crediting health check."""
import secrets
from datetime import timedelta
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from apps.affiliates import services
from apps.affiliates.models import Affiliate, Commission, Referral
from apps.affiliates.testing import backdate_links, per_ticket_mode
from apps.sportsbook.models import Bet, BetSlip

PASSWORD = secrets.token_urlsafe(16)


class Base(TestCase):
    def setUp(self):
        cache.delete(services.HEARTBEAT_KEY)
        self.agent = self.make_agent('agent', 'AGENT')
        self.customer = accounts.create_player(username='customer')
        services.attach_referral(player_id=self.customer.id, code='AGENT')
        backdate_links()
        per_ticket_mode()
        self.agent.refresh_from_db()

    def make_agent(self, username, code):
        player = accounts.create_player(username=username)
        agent = services.apply(player_id=player.id, code=code)
        services.set_status(agent.id, Affiliate.Status.ACTIVE)
        return agent

    def lose(self, stake, settled_ago, player=None, slip=False):
        player = player or self.customer
        if slip:
            return BetSlip.objects.create(wallet='deposit', player_id=player.id, stake=D(stake), combined_odds=D('4'),
                                          status='lost', settled_at=timezone.now() - settled_ago)
        return Bet.objects.create(wallet='deposit', player_id=player.id, stake=D(stake), odds=D('2'), event='x',
                                  status='lost', settled_at=timezone.now() - settled_ago)

    def earned(self, agent=None):
        return sum((c.amount for c in Commission.objects.filter(affiliate=agent or self.agent, kind='stake')), D('0'))


class OutageTests(Base):
    """Workers down for longer than the minute job's 2-day window used to lose
    the agent's share for good."""

    def test_ticket_lost_during_a_four_day_outage_is_recovered_by_the_catch_up(self):
        bet = self.lose('100', timedelta(days=4))
        slip = self.lose('20', timedelta(days=3), slip=True)
        self.assertEqual(services.credit_losing_tickets(), 0)        # outside the minute job's window
        health = services.crediting_health()
        self.assertEqual((health['missing_tickets'], health['missing_amount'], health['agents_affected']), (2, D('36.00'), 1))
        self.assertEqual(services.catch_up_losing_tickets(), 2)
        self.assertEqual(set(Commission.objects.values_list('ticket', flat=True)), {f'S{bet.id}', f'M{slip.id}'})
        self.assertEqual(self.earned(), D('36.00'))
        self.assertEqual(services.catch_up_losing_tickets(), 0)      # never twice
        self.assertEqual(services.crediting_health()['missing_tickets'], 0)

    def test_health_says_whether_the_job_is_running(self):
        self.assertFalse(services.crediting_health()['running'])     # never ran
        services.credit_losing_tickets()
        self.assertTrue(services.crediting_health()['running'])
        later = timezone.now() + timedelta(minutes=10)
        self.assertFalse(services.crediting_health(now=later)['running'])

    def test_a_ticket_the_next_run_will_pay_is_not_flagged(self):
        self.lose('100', timedelta(minutes=4))                       # past the 3-minute delay, inside the slack
        self.assertEqual(services.crediting_health()['missing_tickets'], 0)


class EligibilityTests(Base):
    def test_tickets_lost_while_the_agent_was_suspended_never_count(self):
        services.set_status(self.agent.id, Affiliate.Status.SUSPENDED)
        during = self.lose('100', timedelta(minutes=10))
        services.set_status(self.agent.id, Affiliate.Status.ACTIVE)
        after = self.lose('10', timedelta(seconds=0))
        Bet.objects.filter(pk=after.pk).update(settled_at=timezone.now() + timedelta(seconds=1))
        later = timezone.now() + timedelta(minutes=5)
        self.assertEqual(services.credit_losing_tickets(now=later), 1)
        self.assertEqual(services.catch_up_losing_tickets(now=later), 0)
        self.assertEqual(services.credit_missed_tickets(self.agent.id), 0)
        self.assertEqual(list(Commission.objects.values_list('ticket', flat=True)), [f'S{after.id}'])
        rows = {r['ticket']: r for r in services.ticket_audit(Affiliate.objects.get(pk=self.agent.pk), now=later)['tickets']}
        self.assertEqual((rows[f'S{during.id}']['state'], rows[f'S{during.id}']['reason']), ('not_counted', 'agent_inactive'))
        self.assertEqual(rows[f'S{after.id}']['state'], 'credited')

    def test_audit_explains_every_ticket(self):
        credited = self.lose('10', timedelta(minutes=10))
        services.credit_losing_tickets()
        missed = self.lose('50', timedelta(days=6))
        waiting = self.lose('40', timedelta(minutes=1))
        before = self.lose('5', timedelta(days=31))                  # settled before the customer was linked
        audit = services.ticket_audit(Affiliate.objects.get(pk=self.agent.pk))
        self.assertEqual(audit['counts'], {'credited': 1, 'waiting': 1, 'missing': 1, 'not_counted': 1})
        self.assertEqual(audit['missing_amount'], D('15.00'))
        rows = {r['ticket']: r for r in audit['tickets']}
        self.assertEqual(rows[f'S{credited.id}']['amount'], D('3.00'))
        self.assertEqual(rows[f'S{missed.id}']['state'], 'missing')
        self.assertEqual(rows[f'S{waiting.id}']['state'], 'waiting')
        self.assertEqual(rows[f'S{before.id}']['reason'], 'before_link')
        self.assertEqual(audit['tickets'][0]['ticket'], f'S{waiting.id}')   # newest first


class LinkCustomerTests(Base):
    """A customer who signed up without the agent's link (opened it in the
    WhatsApp browser, registered later in Chrome) earned the agent nothing."""

    def setUp(self):
        super().setUp()
        self.walk_in = accounts.create_player(username='walkin')

    def test_staff_link_counts_from_the_chosen_date(self):
        old = self.lose('100', timedelta(days=5), player=self.walk_in)
        recent = self.lose('20', timedelta(days=2), player=self.walk_in)
        referral, credited = services.link_customer(self.agent.id, self.walk_in.id,
                                                    credit_from=timezone.now() - timedelta(days=3), linked_by='ops')
        self.assertEqual((credited, referral.linked_by, referral.campaign), (1, 'ops', 'staff'))
        self.assertEqual(list(Commission.objects.values_list('ticket', flat=True)), [f'S{recent.id}'])
        rows = {r['ticket']: r for r in services.ticket_audit(Affiliate.objects.get(pk=self.agent.pk))['tickets']}
        self.assertEqual(rows[f'S{old.id}']['reason'], 'before_link')

    def test_default_link_counts_from_now_only(self):
        self.lose('100', timedelta(hours=5), player=self.walk_in)
        _, credited = services.link_customer(self.agent.id, self.walk_in.id)
        self.assertEqual(credited, 0)
        self.assertEqual(services.catch_up_losing_tickets(), 0)

    def test_moving_a_customer_keeps_what_the_old_agent_was_paid(self):
        other = self.make_agent('other', 'OTHER')
        paid_to_first = self.lose('100', timedelta(minutes=10))
        services.credit_losing_tickets()
        services.link_customer(other.id, self.customer.id)
        self.assertEqual(Referral.objects.get(player_id=self.customer.id).affiliate_id, other.id)
        new = self.lose('10', timedelta(seconds=0))
        later = timezone.now() + timedelta(minutes=5)
        Bet.objects.filter(pk=new.pk).update(settled_at=timezone.now() + timedelta(seconds=1))
        services.credit_losing_tickets(now=later)
        owners = dict(Commission.objects.values_list('ticket', 'affiliate_id'))
        self.assertEqual(owners, {f'S{paid_to_first.id}': self.agent.id, f'S{new.id}': other.id})

    def test_refused_links(self):
        with self.assertRaisesMessage(services.AffiliateError, 'own customer'):
            services.link_customer(self.agent.id, self.agent.player_id)
        services.set_status(self.agent.id, Affiliate.Status.SUSPENDED)
        with self.assertRaisesMessage(services.AffiliateError, 'activate'):
            services.link_customer(self.agent.id, self.walk_in.id)

    def test_future_date_is_clamped_to_now(self):
        referral, _ = services.link_customer(self.agent.id, self.walk_in.id, credit_from=timezone.now() + timedelta(days=9))
        self.assertLessEqual(referral.counts_from, timezone.now())


class AdminApiTests(Base):
    def setUp(self):
        super().setUp()
        self.walk_in = accounts.create_player(username='walkin', email='walk@example.com')
        self.api = APIClient()
        self.api.force_authenticate(User.objects.create_user('ops', 'ops@example.com', PASSWORD, is_staff=True))
        self.base = f'/api/admin/affiliates/{self.agent.id}'

    def test_health_audit_and_credit_missed(self):
        self.lose('100', timedelta(days=4))
        health = self.api.get('/api/admin/affiliates/crediting-health/').json()
        self.assertEqual((health['missing_tickets'], health['missing_amount'], health['running']), (1, '30.00', False))
        audit = self.api.get(f'{self.base}/tickets-audit/', {'days': 10}).json()
        self.assertEqual((audit['counts']['missing'], audit['customers']), (1, 1))
        self.assertEqual(self.api.post(f'{self.base}/credit-missed/').json(), {'credited': 1, 'days': 0})
        self.assertEqual(self.api.post('/api/admin/affiliates/credit-missed/').json(), {'credited': 0, 'days': 0})
        self.assertEqual(self.earned(), D('30.00'))

    def test_link_customer_by_username_or_email(self):
        self.lose('10', timedelta(days=1), player=self.walk_in)
        day = (timezone.localdate() - timedelta(days=2)).isoformat()
        res = self.api.post(f'{self.base}/link-customer/', {'player': 'WALKIN', 'credit_from': day}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual((res.json()['player'], res.json()['credited'], res.json()['previous_agent']), ('walkin', 1, None))
        other = self.make_agent('other', 'OTHER')
        res = self.api.post(f'/api/admin/affiliates/{other.id}/link-customer/', {'player': 'walk@example.com'}, format='json')
        self.assertEqual(res.json()['previous_agent'], 'AGENT')
        from apps.accounts.models import AuditLog
        self.assertTrue(AuditLog.objects.filter(event_type='affiliate_customer_linked', player_id=self.walk_in.id).exists())

    def test_bad_input(self):
        url = f'{self.base}/link-customer/'
        self.assertEqual(self.api.post(url, {'player': 'nobody'}, format='json').status_code, 400)
        self.assertEqual(self.api.post(url, {'player': 'walkin', 'credit_from': 'yesterday'}, format='json').status_code, 400)
        self.assertEqual(self.api.post(url, {'player': 'agent'}, format='json').status_code, 400)

    def test_players_cannot_use_it(self):
        api = APIClient()
        api.force_authenticate(accounts.register_player(username='punter', email='p@example.com', password=PASSWORD).user)
        self.assertEqual(api.get('/api/admin/affiliates/crediting-health/').status_code, 403)
        self.assertEqual(api.post(f'{self.base}/link-customer/', {'player': 'walkin'}).status_code, 403)
