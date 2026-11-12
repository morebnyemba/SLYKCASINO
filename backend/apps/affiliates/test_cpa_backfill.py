"""Staff can see every customer's deposit commission for an agent — paid,
waiting, due, or why not — and pay what was missed."""
from decimal import Decimal as D
from itertools import count

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from apps.affiliates import services
from apps.affiliates.models import Affiliate, Commission
from apps.wallet import services as wallet

_k = count()


class DepositCommissionTests(TestCase):
    def setUp(self):
        services.update_programme(welcome_bonus_percent=0, cpa_min_turnover_multiple=1)
        self.agent = services.apply(player_id=accounts.create_player(username='agent').id, code='AGENT')
        services.set_status(self.agent.id, Affiliate.Status.ACTIVE)
        Affiliate.objects.filter(pk=self.agent.pk).update(cpa_percent=D('30'), cpa_cap=D('2'), cpa_amount=0,
                                                          cpa_min_deposit=D('10'))
        self.agent.refresh_from_db()
        self.a = self.customer('alice', deposit='10', bet='10')     # qualifies: 30% of 10 = 3, capped at 2
        self.b = self.customer('bob', deposit='5', bet='5')         # under the 10 minimum
        self.c = self.customer('carol', deposit='20', bet='0')      # hasn't played it through
        self.d = self.customer('dave')                               # no deposit

    def customer(self, name, deposit=None, bet=None):
        p = accounts.create_player(username=name)
        services.attach_referral(player_id=p.id, code='AGENT')
        if deposit:
            wallet.deposit(player_id=p.id, amount=D(deposit), idempotency_key=f'd{next(_k)}')
        if bet and D(bet) > 0:
            wallet.debit(player_id=p.id, amount=D(bet), kind='bet_stake', bucket='deposit', idempotency_key=f'b{next(_k)}')
        return p

    def rows(self):
        return {r['customer']: r for r in services.cpa_audit(Affiliate.objects.get(pk=self.agent.pk))['customers']}

    def test_check_explains_every_customer(self):
        audit = services.cpa_audit(Affiliate.objects.get(pk=self.agent.pk))
        self.assertEqual(audit['counts'], {'paid': 0, 'pending': 0, 'due': 1, 'not_yet': 3})
        self.assertEqual(audit['due_total'], D('2.00'))
        rows = self.rows()
        self.assertEqual((rows['alice']['state'], rows['alice']['amount']), ('due', D('2.00')))
        self.assertIn('of the 10.00 needed', rows['bob']['reason'])
        self.assertIn('bet 0.00 of the 20.00 needed', rows['carol']['reason'])
        self.assertEqual(rows['dave']['reason'], 'no deposit yet')

    def test_pay_what_is_due(self):
        result = services.pay_cpa(self.agent.id, by='ops')
        self.assertEqual(result, {'created': 1, 'approved': 0, 'amount': '2.00'})
        c = Commission.objects.get(affiliate=self.agent, kind='cpa')
        self.assertEqual((c.status, c.amount), (Commission.Status.APPROVED, D('2.00')))
        self.assertIn('paid by ops', c.note)
        self.assertEqual(services.pay_cpa(self.agent.id)['created'], 0)              # never twice
        self.assertEqual(self.rows()['alice']['state'], 'paid')

    def test_waiting_for_approval_is_approved_by_paying(self):
        services.compute_cpa(Affiliate.objects.get(pk=self.agent.pk))                # programme needs approval in tests
        self.assertEqual(self.rows()['alice']['state'], 'pending')
        result = services.pay_cpa(self.agent.id, player_ids=[self.a.id])
        self.assertEqual((result['created'], result['approved']), (0, 1))
        self.assertEqual(self.rows()['alice']['state'], 'paid')

    def test_staff_can_waive_the_rules_for_chosen_customers(self):
        with self.assertRaisesMessage(services.AffiliateError, 'choose the customers'):
            services.pay_cpa(self.agent.id, override=True)
        result = services.pay_cpa(self.agent.id, player_ids=[self.b.id, self.d.id], override=True, by='ops')
        self.assertEqual(result['created'], 1)                                        # bob 30% of 5; dave has no deposit
        c = Commission.objects.get(affiliate=self.agent, kind='cpa')
        self.assertEqual(c.amount, D('1.50'))
        self.assertIn('rules waived', c.note)

    def test_zero_terms_are_explained(self):
        Affiliate.objects.filter(pk=self.agent.pk).update(cpa_percent=0)
        self.assertIn('0%', self.rows()['alice']['reason'])
        self.assertEqual(services.pay_cpa(self.agent.id)['created'], 0)

    def test_admin_api(self):
        api = APIClient()
        api.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x' * 12, is_staff=True))
        url = f'/api/admin/affiliates/{self.agent.id}/deposit-commissions/'
        body = api.get(url).json()
        self.assertEqual((body['due_total'], len(body['customers'])), ('2.00', 4))
        self.assertEqual(api.post(url, {}, format='json').json()['amount'], '2.00')
        res = api.post(url, {'player_ids': [self.c.id], 'override': True}, format='json').json()
        self.assertEqual(res['created'], 1)
        from apps.accounts.models import AuditLog
        self.assertEqual(AuditLog.objects.filter(event_type='affiliate_cpa_paid_by_staff').count(), 2)
        self.assertEqual(api.post(url, {'override': True}, format='json').status_code, 400)
