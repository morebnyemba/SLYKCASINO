"""No affiliate list hides anyone: every list pages, staff can search."""
import secrets
from datetime import timedelta
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from apps.affiliates import services
from apps.affiliates.models import Affiliate, Commission, Payout

PW = secrets.token_urlsafe(16)


class AdminListTests(TestCase):
    def setUp(self):
        for i in range(30):
            a = services.apply(player_id=accounts.create_player(username=f'agent{i:02d}').id, code=f'CODE{i:02d}')
            services.set_status(a.id, Affiliate.Status.ACTIVE)
            Commission.objects.create(affiliate=a, kind='cpa', base_amount=D('10'), rate=D('30'), amount=D('2'), status='approved')
            Payout.objects.create(affiliate=a, amount=D('1'), method='ecocash', account_number='0771234567')
        self.api = APIClient()
        self.api.force_authenticate(User.objects.create_user('ops', 'o@example.com', PW, is_staff=True))

    def test_every_agent_is_reachable(self):
        first = self.api.get('/api/admin/affiliates/', {'status': 'active'}).json()
        self.assertEqual((first['count'], len(first['results'])), (30, 25))
        second = self.api.get('/api/admin/affiliates/', {'status': 'active', 'page': 2}).json()
        self.assertEqual(len(second['results']), 5)
        self.assertEqual(len(self.api.get('/api/admin/affiliates/', {'page_size': 100}).json()['results']), 30)
        self.assertEqual(len(self.api.get('/api/admin/affiliates/', {'page_size': 5000}).json()['results']), 30)  # capped at 200

    def test_search_by_code_or_username(self):
        self.assertEqual([a['code'] for a in self.api.get('/api/admin/affiliates/', {'q': 'code07'}).json()['results']], ['CODE07'])
        self.assertEqual(self.api.get('/api/admin/affiliates/', {'q': 'agent1'}).json()['count'], 10)

    def test_commissions_and_payouts_page_too(self):
        self.assertEqual(self.api.get('/api/admin/affiliate-commissions/', {'status': 'approved'}).json()['count'], 30)
        self.assertEqual(len(self.api.get('/api/admin/affiliate-payouts/', {'page': 2}).json()['results']), 5)
        self.assertEqual(self.api.get('/api/admin/affiliate-payouts/', {'q': 'CODE03'}).json()['count'], 1)


class AgentListTests(TestCase):
    def setUp(self):
        self.agent_player = accounts.register_player(username='agent', email='a@example.com', password=PW)
        self.agent = services.apply(player_id=self.agent_player.id, code='AGENT')
        services.set_status(self.agent.id, Affiliate.Status.ACTIVE)
        for i in range(120):
            services.attach_referral(player_id=accounts.create_player(username=f'cust{i:03d}').id, code='AGENT')
        for i in range(60):
            Commission.objects.create(affiliate=self.agent, kind='netloss', period=timezone.localdate() - timedelta(days=i), base_amount=D('10'),
                                      rate=D('30'), amount=D('3'), status='approved')
        self.api = APIClient()
        self.api.force_authenticate(self.agent_player.user)

    def test_all_245_style_customers_are_listed_page_by_page(self):
        body = self.api.get('/api/affiliates/me/customers/', {'page_size': 50, 'page': 3}).json()
        self.assertEqual((body['count'], len(body['results'])), (120, 20))
        self.assertEqual(body['results'][0]['player'][:2], 'cu')
        self.assertIn('*', body['results'][0]['player'])            # masked for the agent
        self.assertEqual(self.api.get('/api/affiliates/me/customers/', {'q': 'cust01'}).json()['count'], 10)

    def test_full_history_pages(self):
        body = self.api.get('/api/affiliates/me/history/', {'page': 3}).json()
        self.assertEqual((body['count'], len(body['results'])), (60, 10))
        self.assertEqual(self.api.get('/api/affiliates/me/history/', {'kind': 'payouts'}).json()['count'], 0)

    def test_players_who_arent_agents_get_404(self):
        api = APIClient()
        api.force_authenticate(accounts.register_player(username='p', email='p@example.com', password=PW).user)
        self.assertEqual(api.get('/api/affiliates/me/customers/').status_code, 404)
