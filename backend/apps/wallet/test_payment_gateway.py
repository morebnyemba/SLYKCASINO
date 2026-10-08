"""Paynow credentials and the live gateway, set from the admin console."""
from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog
from apps.wallet import paynow, payments
from apps.wallet.models import PaymentGateway, PaymentTransaction
from apps.wallet.test_paynow import KEY, _FakeResponse, _player, signed

NO_ENV = override_settings(PSP_PROVIDER='stub', PAYNOW_INTEGRATION_ID='', PAYNOW_INTEGRATION_KEY='',
                           PAYNOW_AUTH_EMAIL='', FRONTEND_URL='https://betblits.test')


@NO_ENV
class GatewaySettingsTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.api.force_authenticate(User.objects.create_superuser('payops', 'p@example.com', 'pw'))

    def put(self, **body):
        return self.api.put('/api/admin/payment-gateway/', body, format='json')

    def test_saved_credentials_switch_paynow_on(self):
        res = self.put(paynow_integration_id='1201', paynow_integration_key=KEY,
                       paynow_auth_email='merchant@example.com', provider='paynow')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(res.data['provider'], 'paynow')
        self.assertTrue(res.data['paynow']['configured'])
        self.assertEqual(res.data['paynow']['key_hint'], f'••••{KEY[-4:]}')
        self.assertNotIn(KEY, str(res.data))  # the key never comes back
        self.assertEqual(res.data['paynow']['result_url'], 'https://betblits.test/api/wallet/paynow/result/')
        self.assertTrue(payments.gateway_enabled())
        self.assertEqual(paynow.get_config().integration_key, KEY)
        self.assertTrue(AuditLog.objects.filter(event_type='payment_settings').exists())

    def test_paynow_refused_without_credentials(self):
        res = self.put(provider='paynow')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(payments.gateway_enabled())
        self.assertEqual(PaymentGateway.load().provider, '')

    def test_switching_to_test_processor_needs_confirmation(self):
        self.put(paynow_integration_id='1201', paynow_integration_key=KEY, provider='paynow')
        self.assertEqual(self.put(provider='stub').status_code, 400)
        self.assertTrue(payments.gateway_enabled())
        self.assertEqual(self.put(provider='stub', confirm_test_mode=True).status_code, 200)
        self.assertFalse(payments.gateway_enabled())

    def test_blank_admin_fields_fall_back_to_server_env(self):
        with override_settings(PSP_PROVIDER='paynow', PAYNOW_INTEGRATION_ID='999', PAYNOW_INTEGRATION_KEY='env-key-1234'):
            data = self.api.get('/api/admin/payment-gateway/').data
            self.assertEqual(data['provider'], 'paynow')
            self.assertEqual(data['paynow']['integration_id'], '999')
            self.assertTrue(data['paynow']['from_server']['integration_key'])
            # Saving an ID here overrides the env one; the env key still applies.
            self.put(paynow_integration_id='1201')
            self.assertEqual(paynow.get_config().integration_id, '1201')
            self.assertEqual(paynow.get_config().integration_key, 'env-key-1234')

    def test_validation(self):
        self.assertEqual(self.put(paynow_integration_id='abc').status_code, 400)
        self.assertEqual(self.put(paynow_auth_email='not-an-email').status_code, 400)

    def test_connection_test(self):
        self.assertFalse(self.api.post('/api/admin/payment-gateway/test/').data['ok'])
        self.put(paynow_integration_id='1201', paynow_integration_key=KEY)
        ok = signed([('status', 'Ok'), ('browserurl', 'https://www.paynow.co.zw/payment/x'),
                     ('pollurl', 'https://www.paynow.co.zw/interface/checkpayment/?guid=t'), ('paynowreference', '4242')])
        with patch('apps.wallet.paynow.requests.post', return_value=_FakeResponse(ok)):
            res = self.api.post('/api/admin/payment-gateway/test/')
        self.assertEqual((res.data['ok'], res.data['paynow_reference']), (True, '4242'))
        self.assertFalse(PaymentTransaction.objects.exists())  # nothing recorded as a deposit
        with patch('apps.wallet.paynow.requests.post', return_value=_FakeResponse('status=Error&error=Invalid+Id.')):
            res = self.api.post('/api/admin/payment-gateway/test/')
        self.assertEqual((res.data['ok'], res.data['error']), (False, 'Invalid Id.'))

    def test_players_cannot_read_or_change_it(self):
        _, user = _player('peeker')
        api = APIClient()
        api.force_authenticate(user)
        self.assertEqual(api.get('/api/admin/payment-gateway/').status_code, 403)
        self.assertEqual(api.put('/api/admin/payment-gateway/', {'provider': 'stub'}, format='json').status_code, 403)


@NO_ENV
class DepositWithSavedCredentialsTests(TestCase):
    def test_deposit_goes_to_paynow_with_admin_credentials(self):
        PaymentGateway.objects.create(pk=1, provider='paynow', paynow_integration_id='1201',
                                      paynow_integration_key=KEY, paynow_auth_email='merchant@example.com')
        _, user = _player('saved_creds')
        api = APIClient()
        api.force_authenticate(user)
        reply = signed([('status', 'Ok'), ('instructions', 'Approve on your phone'), ('paynowreference', '77'),
                        ('pollurl', 'https://www.paynow.co.zw/interface/checkpayment/?guid=z')])
        with patch('apps.wallet.paynow.requests.post', return_value=_FakeResponse(reply)) as post:
            res = api.post('/api/wallet/deposit/', {'amount': '10', 'method': 'ecocash', 'phone': '0771234567'}, format='json')
        self.assertEqual(res.status_code, 202, res.data)
        self.assertIn('id=1201', post.call_args.kwargs['data'])
