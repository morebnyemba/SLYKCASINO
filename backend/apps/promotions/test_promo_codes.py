"""Promo codes: staff manage them; players enter one when depositing."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as account_services
from apps.promotions.models import DepositBonus, PromoCode, PromoRedemption
from apps.wallet import services as wallet_services
from apps.wallet.models import PaymentTransaction

D = Decimal


class PromoCodeTests(TestCase):
    def setUp(self):
        self.staff = APIClient()
        self.staff.force_authenticate(User.objects.create_user('promo_admin', 'p@example.com', 'x', is_staff=True))
        self.player = account_services.create_player(username='punter')
        self.player.user = User.objects.create(username='punter')
        self.player.save(update_fields=['user'])
        self.api = APIClient()
        self.api.force_authenticate(self.player.user)

    def create(self, **kw):
        body = {'code': 'welcome50', 'name': 'Welcome 50%', 'kind': 'percent', 'value': '50', 'max_bonus': '20',
                'min_deposit': '5', **kw}
        return self.staff.post('/api/admin/promo-codes/', body, format='json')

    def deposit(self, amount, code=''):
        return self.api.post('/api/wallet/deposit/', {'amount': amount, 'promo_code': code}, format='json')

    def bonus(self):
        return wallet_services.get_balances(self.player.id)['bonus']

    def test_staff_create_and_the_code_is_stored_upper_case(self):
        res = self.create()
        self.assertEqual((res.status_code, res.json()['code']), (201, 'WELCOME50'))
        self.assertEqual(self.create().status_code, 400)                        # duplicate
        self.assertEqual(self.create(code='x').status_code, 400)                # too short
        self.assertEqual(self.create(code='NEG', value='-5').status_code, 400)
        self.assertEqual(APIClient().get('/api/admin/promo-codes/').status_code, 401)
        self.assertEqual(self.api.get('/api/admin/promo-codes/').status_code, 403)

    def test_deposit_with_a_code_pays_its_bonus_into_the_bonus_wallet(self):
        self.create()
        check = self.api.post('/api/promo-codes/check/', {'code': 'Welcome50', 'amount': '30'}, format='json').json()
        self.assertEqual((check['valid'], check['bonus']), (True, '15.00'))
        self.assertEqual(self.deposit('30', 'welcome50').status_code, 201)
        self.assertEqual(self.bonus(), D('15.00'))
        self.assertEqual(self.deposit('100', 'WELCOME50').json()['detail'], 'You’ve already used that promo code.')
        row = self.staff.get('/api/admin/promo-codes/').json()[0]
        self.assertEqual((row['uses'], row['total_given']), (1, '15.00'))

    def test_a_code_replaces_the_automatic_deposit_bonus(self):
        DepositBonus.objects.create(name='Auto 100%', min_deposit=D('1'), percent=D('100'))
        self.create(code='FIXED5', kind='fixed', value='5')
        self.deposit('30', 'FIXED5')
        self.assertEqual(self.bonus(), D('5.00'))                               # not 5 + 30
        self.deposit('30')                                                      # no code: the automatic one
        self.assertEqual(self.bonus(), D('35.00'))

    def test_limits_dates_and_deactivation(self):
        promo_id = self.create(max_uses=1).json()['id']
        self.assertIn('at least $5.00', self.deposit('2', 'WELCOME50').json()['detail'])
        other = account_services.create_player(username='other')
        PromoRedemption.objects.create(promo_id=promo_id, player_id=other.id, deposit_entry_id=999999,
                                       deposit_amount=D('10'), bonus_amount=D('5'))
        self.assertIn('fully used', self.deposit('10', 'WELCOME50').json()['detail'])
        self.create(code='LATER', starts_at=(timezone.now() + timedelta(days=1)).isoformat())
        self.assertIn('isn’t active yet', self.deposit('10', 'LATER').json()['detail'])
        off = self.create(code='OFF').json()['id']
        self.assertEqual(self.staff.patch(f'/api/admin/promo-codes/{off}/', {'active': False}, format='json').status_code, 200)
        self.assertIn('isn’t valid', self.deposit('10', 'OFF').json()['detail'])
        self.assertEqual(self.staff.delete(f'/api/admin/promo-codes/{promo_id}/').status_code, 409)  # used: deactivate
        self.assertEqual(self.staff.delete(f'/api/admin/promo-codes/{off}/').status_code, 204)

    def test_a_code_that_expired_before_the_money_landed_still_credits_the_deposit(self):
        from apps.promotions import promo_codes
        self.create(code='SHORT')
        txn = PaymentTransaction.objects.create(reference='DEPX', player_id=self.player.id, method='ecocash',
                                                amount=D('20'), promo_code='SHORT')
        PromoCode.objects.filter(code='SHORT').update(active=False)
        wallet_services.deposit(player_id=self.player.id, amount=D('20'), idempotency_key='late',
                                reference=f'psp:paynow:{txn.reference}')
        self.assertEqual(wallet_services.get_balances(self.player.id)['deposit'], D('20.00'))
        self.assertEqual(self.bonus(), D('0.00'))
        self.assertFalse(PromoRedemption.objects.exists())
        # A redelivered callback never pays a bonus twice.
        self.assertIsNone(promo_codes.apply_to_deposit(player_id=self.player.id, code='SHORT', amount=D('20'),
                                                       deposit_entry_id=1))

    def test_same_code_on_accounts_sharing_a_payment_number_is_refused(self):
        from apps.risk.models import RiskSignal
        self.create(code='ONCE', kind='fixed', value='5')
        twin = account_services.create_player(username='twin')
        for p, ref in ((twin, 'T1'), (self.player, 'T2')):
            txn = PaymentTransaction.objects.create(reference=ref, player_id=p.id, method='ecocash', phone='0771234567',
                                                    amount=D('10'), promo_code='ONCE')
            wallet_services.deposit(player_id=p.id, amount=D('10'), idempotency_key=f'd{ref}',
                                    reference=f'psp:paynow:{txn.reference}')
        self.assertEqual(wallet_services.get_balances(twin.id)['bonus'], D('5.00'))
        self.assertEqual(self.bonus(), D('0.00'))
        self.assertTrue(RiskSignal.objects.filter(player_id=self.player.id).exists())

    def test_checking_codes_is_rate_limited(self):
        codes = [self.api.post('/api/promo-codes/check/', {'code': f'GUESS{i}'}, format='json').status_code
                 for i in range(21)]
        self.assertEqual(codes[-1], 429)
