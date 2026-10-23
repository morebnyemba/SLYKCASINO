"""The admin dashboard's profit for a period."""
from datetime import timedelta
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from apps.affiliates import services
from apps.affiliates.models import Affiliate, Commission
from apps.wallet import services as wallet


class ProfitTests(TestCase):
    def setUp(self):
        services.update_programme(welcome_bonus_percent=0)
        p = accounts.create_player(username='punter')
        wallet.deposit(player_id=p.id, amount=D('100'), idempotency_key='dep')
        wallet.debit(player_id=p.id, amount=D('60'), kind='bet_stake', idempotency_key='s1')
        wallet.credit(player_id=p.id, amount=D('20'), kind='bet_payout', idempotency_key='p1')
        wallet.debit(player_id=p.id, amount=D('10'), kind='casino_debit', idempotency_key='s2')
        wallet.credit(player_id=p.id, amount=D('5'), kind='bonus', idempotency_key='b1')
        agent = accounts.create_player(username='agent')
        a = services.apply(player_id=agent.id, code='AGENT')
        services.set_status(a.id, Affiliate.Status.ACTIVE)
        today = timezone.localdate()
        Commission.objects.create(affiliate=a, kind=Commission.Kind.STAKE, ticket='S1', period=today, amount=D('6'))
        Commission.objects.create(affiliate=a, kind=Commission.Kind.STAKE, ticket='S2', period=today - timedelta(days=5), amount=D('99'))
        Commission.objects.create(affiliate=a, kind=Commission.Kind.CPA, amount=D('50'), status='rejected')
        self.api = APIClient()
        self.api.force_authenticate(User.objects.create_user('ops', 'ops@example.com', 'x', is_staff=True))

    def test_today(self):
        body = self.api.get('/api/admin/profit/').json()
        self.assertEqual((body['stakes'], body['payouts'], body['ggr']), ('70.00', '20.00', '50.00'))
        self.assertEqual((body['sportsbook']['ggr'], body['aviator']['ggr']), ('40.00', '10.00'))
        self.assertEqual((body['bonuses'], body['agent_commission'], body['profit']), ('5.00', '6.00', '39.00'))
        self.assertEqual(body['cash'], {'deposits': '100.00', 'withdrawals': '0.00', 'net': '100.00'})

    def test_week_counts_older_commission_and_staff_only(self):
        self.assertEqual(self.api.get('/api/admin/profit/', {'frame': '7d'}).json()['agent_commission'], '105.00')
        self.assertEqual(self.api.get('/api/admin/profit/', {'frame': 'nonsense'}).status_code, 400)
        self.assertEqual(APIClient().get('/api/admin/profit/').status_code, 401)
