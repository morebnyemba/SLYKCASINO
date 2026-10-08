"""Admin-editable payment methods: what players are offered, the limits the
API enforces, and the admin endpoints."""
from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.wallet.models import LedgerEntry, PaymentMethod
from apps.wallet.test_paynow import PAYNOW, _player

STUB = override_settings(PSP_PROVIDER='stub')


@STUB
class OfferedMethodsTests(TestCase):
    def setUp(self):
        self.player, self.user = _player('methods_punter')
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def test_seeded_methods_are_offered_in_admin_order(self):
        res = self.api.get('/api/wallet/payment-methods/')
        self.assertEqual(res.status_code, 200)
        self.assertEqual([m['code'] for m in res.data['deposit']], ['ecocash', 'onemoney', 'innbucks', 'card', 'usdt'])
        self.assertIn('EcoCash', res.data['footer'])

    def test_switched_off_method_is_hidden_and_refused(self):
        PaymentMethod.objects.filter(code='onemoney').update(deposit_enabled=False, show_in_footer=False)
        res = self.api.get('/api/wallet/payment-methods/')
        self.assertNotIn('onemoney', [m['code'] for m in res.data['deposit']])
        self.assertNotIn('OneMoney', res.data['footer'])
        self.assertNotIn('onemoney', self.api.get('/api/wallet/').data['deposit_methods'])
        res = self.api.post('/api/wallet/deposit/', {'amount': '10', 'method': 'onemoney'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertFalse(LedgerEntry.objects.filter(kind='deposit').exists())

    def test_limits_are_enforced(self):
        PaymentMethod.objects.filter(code='ecocash').update(min_deposit=5, max_deposit=100)
        low = self.api.post('/api/wallet/deposit/', {'amount': '2', 'method': 'ecocash'}, format='json')
        self.assertEqual(low.status_code, 400)
        self.assertIn('minimum', low.data['detail'])
        high = self.api.post('/api/wallet/deposit/', {'amount': '150', 'method': 'ecocash'}, format='json')
        self.assertEqual(high.status_code, 400)
        ok = self.api.post('/api/wallet/deposit/', {'amount': '50', 'method': 'ecocash'}, format='json')
        self.assertEqual(ok.status_code, 201)

    @PAYNOW
    def test_live_gateway_only_offers_what_it_can_process(self):
        codes = [m['code'] for m in self.api.get('/api/wallet/payment-methods/').data['deposit']]
        self.assertEqual(codes, ['ecocash', 'onemoney', 'innbucks', 'card'])  # Paynow can't take USDT
        res = self.api.post('/api/wallet/deposit/', {'amount': '10', 'method': 'usdt'}, format='json')
        self.assertEqual(res.status_code, 400)


@STUB
class AdminPaymentMethodTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_superuser('ops', 'ops@example.com', 'pw')
        self.api = APIClient()
        self.api.force_authenticate(self.admin)

    def test_list_reports_gateway(self):
        res = self.api.get('/api/admin/payment-methods/')
        self.assertEqual(res.data['gateway'], 'stub')
        self.assertEqual(len(res.data['results']), 5)
        self.assertTrue(all(m['gateway_supported'] for m in res.data['results']))

    def test_edit_and_create(self):
        ecocash = PaymentMethod.objects.get(code='ecocash')
        res = self.api.patch(f'/api/admin/payment-methods/{ecocash.id}/', {
            'name': 'EcoCash USD', 'min_deposit': '2.00', 'color': '#E2231A',
        }, format='json')
        self.assertEqual(res.status_code, 200, res.data)
        ecocash.refresh_from_db()
        self.assertEqual((ecocash.name, str(ecocash.min_deposit), ecocash.color), ('EcoCash USD', '2.00', '#e2231a'))

        res = self.api.post('/api/admin/payment-methods/', {
            'code': 'zipit', 'name': 'ZIPIT', 'field': 'none', 'color': '#123456', 'deposit_enabled': False,
        }, format='json')
        self.assertEqual(res.status_code, 201, res.data)

    def test_validation(self):
        pm = PaymentMethod.objects.get(code='card')
        bad = self.api.patch(f'/api/admin/payment-methods/{pm.id}/', {'color': 'red'}, format='json')
        self.assertEqual(bad.status_code, 400)
        bad = self.api.patch(f'/api/admin/payment-methods/{pm.id}/', {'min_deposit': '10', 'max_deposit': '5'}, format='json')
        self.assertEqual(bad.status_code, 400)

    def test_players_cannot_edit(self):
        _, user = _player('nosy')
        api = APIClient()
        api.force_authenticate(user)
        self.assertEqual(api.get('/api/admin/payment-methods/').status_code, 403)
