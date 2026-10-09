"""Affiliate balance and payout requests: instant to the betting wallet,
operator-sent to mobile money / bank, and the admin queue."""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts import services as account_services
from apps.accounts.models import AuditLog
from apps.affiliates import services
from apps.affiliates.models import Affiliate, Commission, Payout
from apps.wallet import services as wallet_services

D = Decimal


class PayoutBase(TestCase):
    def setUp(self):
        services.update_programme(min_payout=10, external_payouts=True, welcome_bonus_percent=0)
        self.partner = account_services.create_player(username='partner')
        self.affiliate = services.apply(player_id=self.partner.id, code='PARTNER')
        services.set_status(self.affiliate.id, Affiliate.Status.ACTIVE)
        self.affiliate.refresh_from_db()
        self.earn('50.00')

    def earn(self, amount):
        c = Commission.objects.create(affiliate=self.affiliate, kind=Commission.Kind.CPA, amount=D(amount))
        return services.approve(c.id)

    def verify_kyc(self):
        self.partner.kyc_status = self.partner.Kyc.VERIFIED
        self.partner.save(update_fields=['kyc_status'])

    def available(self):
        return services.balance(self.affiliate)['available']

    def request(self, **kw):
        return services.request_payout(affiliate_id=self.affiliate.id, **kw)


class WalletPayoutTests(PayoutBase):
    def test_instant_and_never_more_than_available(self):
        payout = self.request(amount='20', method='wallet')
        self.assertEqual(payout.status, Payout.Status.PAID)
        self.assertEqual(wallet_services.get_balance(self.partner.id), D('20.00'))
        self.assertEqual(self.available(), D('30.00'))
        with self.assertRaisesMessage(services.AffiliateError, 'you can withdraw up to 30.00'):
            self.request(amount='30.01', method='wallet')
        self.request(amount='30', method='wallet')
        self.assertEqual((self.available(), services.balance(self.affiliate)['paid_out']), (D('0'), D('50.00')))

    def test_pending_commissions_are_not_withdrawable(self):
        Commission.objects.create(affiliate=self.affiliate, kind=Commission.Kind.CPA, amount=D('99'))
        self.assertEqual((self.available(), services.balance(self.affiliate)['pending']), (D('50.00'), D('99.00')))

    def test_legacy_paid_commissions_count_as_paid_not_available(self):
        Commission.objects.create(affiliate=self.affiliate, kind=Commission.Kind.CPA, amount=D('40'),
                                  status=Commission.Status.PAID)
        b = services.balance(self.affiliate)
        self.assertEqual((b['available'], b['paid_out']), (D('50.00'), D('40.00')))

    def test_only_active_affiliates(self):
        services.set_status(self.affiliate.id, Affiliate.Status.SUSPENDED)
        with self.assertRaises(services.AffiliateError):
            self.request(amount='10', method='wallet')

    def test_bad_input(self):
        for amount in ('0', '-5', 'abc'):
            with self.assertRaises(services.AffiliateError):
                self.request(amount=amount, method='wallet')
        with self.assertRaises(services.AffiliateError):
            self.request(amount='10', method='paypal')


class ExternalPayoutTests(PayoutBase):
    def test_needs_kyc_minimum_and_a_valid_number(self):
        with self.assertRaisesMessage(services.AffiliateError, 'verify your identity'):
            self.request(amount='20', method='ecocash', account_number='0771234567')
        self.verify_kyc()
        with self.assertRaisesMessage(services.AffiliateError, 'minimum payout'):
            self.request(amount='5', method='ecocash', account_number='0771234567')
        with self.assertRaisesMessage(services.AffiliateError, 'mobile number'):
            self.request(amount='20', method='ecocash', account_number='12')
        with self.assertRaisesMessage(services.AffiliateError, 'bank'):
            self.request(amount='20', method='bank', account_number='12345678')

    def test_requested_then_paid_or_rejected(self):
        self.verify_kyc()
        p1 = self.request(amount='20', method='ecocash', account_name='Tendai M', account_number='077 123 4567')
        self.assertEqual((p1.status, p1.account_number), (Payout.Status.REQUESTED, '0771234567'))
        self.assertEqual(self.available(), D('30.00'))                 # held while requested
        self.assertEqual(wallet_services.get_balance(self.partner.id), D('0'))

        services.mark_payout_paid(p1.id, reference='MP2410.1234.A')
        p1.refresh_from_db()
        self.assertEqual((p1.status, p1.reference), (Payout.Status.PAID, 'MP2410.1234.A'))
        with self.assertRaises(services.AffiliateError):
            services.reject_payout(p1.id)

        p2 = self.request(amount='30', method='bank', bank_name='CBZ', account_name='Tendai M', account_number='0123456789')
        self.assertEqual(self.available(), D('0'))
        services.reject_payout(p2.id, note='Account name does not match')
        self.assertEqual(self.available(), D('30.00'))                 # back in the balance

    def test_can_be_switched_off(self):
        self.verify_kyc()
        services.update_programme(external_payouts=False)
        with self.assertRaisesMessage(services.AffiliateError, 'switched off'):
            self.request(amount='20', method='ecocash', account_number='0771234567')
        self.assertEqual([m['id'] for m in services.payout_options(self.affiliate)['methods']], ['wallet'])


class PayoutApiTests(PayoutBase):
    def client_for(self, player, staff=False):
        user = User.objects.create_user(username=player.username, password='pw', is_staff=staff)
        player.user = user
        player.save(update_fields=['user'])
        api = APIClient()
        api.force_authenticate(user)
        return api

    def test_affiliate_and_admin_flow(self):
        self.verify_kyc()
        api = self.client_for(self.partner)
        me = api.get('/api/affiliates/me/').json()
        self.assertEqual(me['balance']['available'], '50.00')
        self.assertIn('ecocash', [m['id'] for m in me['payout_options']['methods']])

        res = api.post('/api/affiliates/me/payouts/', {'amount': '15', 'method': 'wallet'}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.json()['balance']['available'], '35.00')
        res = api.post('/api/affiliates/me/payouts/', {'amount': '999', 'method': 'wallet'}, format='json')
        self.assertEqual(res.status_code, 400)
        res = api.post('/api/affiliates/me/payouts/', {'amount': '25', 'method': 'onemoney', 'account_number': '0712345678'}, format='json')
        self.assertEqual(res.status_code, 201)
        payout_id = res.json()['payout']['id']
        self.assertEqual(api.get('/api/admin/affiliate-payouts/').status_code, 403)

        staff = User.objects.create_user('staff', 'staff@example.com', 'x', is_staff=True)
        admin = APIClient()
        admin.force_authenticate(staff)
        queue = admin.get('/api/admin/affiliate-payouts/', {'status': 'requested'}).json()
        rows = queue.get('results', queue)
        self.assertEqual([(r['id'], r['username'], r['kyc_status']) for r in rows], [(payout_id, 'partner', 'verified')])
        res = admin.post(f'/api/admin/affiliate-payouts/{payout_id}/mark-paid/', {'reference': 'OM-77'}, format='json')
        self.assertEqual((res.status_code, res.json()['status']), (200, 'paid'))
        self.assertEqual(admin.post(f'/api/admin/affiliate-payouts/{payout_id}/reject/', {}, format='json').status_code, 400)
        self.assertTrue(AuditLog.objects.filter(event_type='affiliate_payout_paid').exists())
        self.assertEqual(admin.get('/api/admin/stats/').json()['queues']['payouts_pending'], 0)
