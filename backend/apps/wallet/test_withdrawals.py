"""Withdrawal requests: held on request, paid or rejected by staff, and only
paid ones count as withdrawals in reports."""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as account_services
from apps.accounts.models import AuditLog
from apps.notifications.models import Notification
from apps.wallet import reporting, services, withdrawals
from apps.wallet.models import LedgerEntry, WithdrawalRequest, WithdrawalSettings

D = Decimal
ECOCASH = {'method': 'ecocash', 'account_number': '077 123 4567', 'account_name': 'Tendai M'}


class WithdrawalTests(TestCase):
    def setUp(self):
        self.player = account_services.create_player(username='tendai')
        self.player.kyc_status = self.player.Kyc.VERIFIED
        self.user = User.objects.create(username='tendai')
        self.player.user = self.user
        self.player.save(update_fields=['kyc_status', 'user'])
        services.deposit(player_id=self.player.id, amount=D('200'), idempotency_key='dep:1')
        self.api = APIClient()
        self.api.force_authenticate(self.user)
        self.staff = APIClient()
        self.staff.force_authenticate(User.objects.create_user('cashier', 'c@example.com', 'pw', is_staff=True))

    def ask(self, amount, **dest):
        return self.api.post('/api/wallet/withdraw/', {'amount': amount, **(dest or ECOCASH)}, format='json')

    def kpis(self):
        return reporting.ledger_kpis([self.player.id], None, timezone.now() + timezone.timedelta(seconds=1))

    def test_request_holds_then_paid_counts_as_withdrawal(self):
        res = self.ask('50')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()['balance'], '150.00')
        rid = res.json()['withdrawal']['id']
        self.assertEqual(res.json()['withdrawal']['account_number'], '••4567')
        self.assertEqual(self.kpis()['withdrawals'], '0.00')  # held, not yet paid

        queue = self.staff.get('/api/admin/withdrawals/').json()
        row = queue['results'][0]
        self.assertEqual((row['id'], row['username'], row['account_number'], row['kyc_status']),
                         (rid, 'tendai', '0771234567', 'verified'))
        self.assertEqual(row['context']['deposits'], '200.00')
        self.assertEqual(queue['pending_total'], '50.00')

        self.assertEqual(self.staff.post(f'/api/admin/withdrawals/{rid}/mark-paid/', {'reference': ''}, format='json').status_code, 400)
        res = self.staff.post(f'/api/admin/withdrawals/{rid}/mark-paid/', {'reference': 'MP241011.1200.A1'}, format='json')
        self.assertEqual((res.status_code, res.json()['status']), (200, 'paid'))
        self.assertEqual(services.get_balance(self.player.id), D('150.00'))
        k = self.kpis()
        self.assertEqual((k['withdrawals'], k['withdrawal_count']), ('50.00', 1))
        self.assertEqual(self.staff.post(f'/api/admin/withdrawals/{rid}/reject/', {'note': 'oops'}, format='json').status_code, 409)
        self.assertTrue(AuditLog.objects.filter(event_type='withdrawal_paid').exists())
        self.assertTrue(Notification.objects.filter(player_id=self.player.id, title='Withdrawal sent').exists())
        self.assertEqual(self.staff.get('/api/admin/stats/').json()['queues']['withdrawals_pending'], 0)

    def test_reject_and_cancel_return_the_money(self):
        a = self.ask('30').json()['withdrawal']['id']
        b = self.ask('20').json()['withdrawal']['id']
        self.assertEqual(services.get_balance(self.player.id), D('150.00'))
        self.assertEqual(self.staff.post(f'/api/admin/withdrawals/{a}/reject/', {'note': ''}, format='json').status_code, 400)
        self.staff.post(f'/api/admin/withdrawals/{a}/reject/', {'note': 'Name doesn’t match the account'}, format='json')
        self.assertEqual(self.api.post(f'/api/wallet/withdrawals/{b}/cancel/').json()['balance'], '200.00')
        self.assertEqual(self.api.post(f'/api/wallet/withdrawals/{b}/cancel/').status_code, 409)
        self.assertEqual(self.kpis()['withdrawals'], '0.00')
        mine = self.api.get('/api/wallet/withdrawals/').json()
        self.assertEqual([r['status'] for r in mine['results']], ['cancelled', 'rejected'])
        self.assertEqual(mine['results'][1]['note'], 'Name doesn’t match the account')
        # The ledger nets to zero for both.
        held = sum(LedgerEntry.objects.filter(kind='withdrawal_hold').values_list('amount', flat=True))
        self.assertEqual(held, D('0'))

    def test_validation_and_limits(self):
        self.assertIn('mobile number', self.ask('10', method='ecocash', account_number='12').json()['detail'])
        self.assertIn('bank', self.ask('10', method='bank', account_number='123456').json()['detail'])
        self.assertEqual(self.ask('10', method='paypal', account_number='x').status_code, 400)
        cfg = WithdrawalSettings.load()
        cfg.min_amount, cfg.max_amount, cfg.daily_max = D('5'), D('100'), D('120')
        cfg.save()
        self.assertIn('minimum', self.ask('2').json()['detail'])
        self.assertIn('at once', self.ask('150').json()['detail'])
        self.assertEqual(self.ask('100').status_code, 201)
        self.assertIn('$20.00 left today', self.ask('30').json()['detail'])
        self.assertEqual(self.ask('30', method='bank', account_number='0123456789', bank_name='CBZ', account_name='T M').status_code, 400)
        self.player.kyc_status = self.player.Kyc.PENDING
        self.player.save(update_fields=['kyc_status'])
        self.assertEqual(self.ask('10').status_code, 403)

    def test_players_cant_touch_the_queue(self):
        self.assertEqual(self.api.get('/api/admin/withdrawals/').status_code, 403)
        rid = self.ask('10').json()['withdrawal']['id']
        self.assertEqual(self.api.post(f'/api/admin/withdrawals/{rid}/mark-paid/', {'reference': 'abc'}).status_code, 403)
        other = account_services.create_player(username='other')
        with self.assertRaises(withdrawals.WithdrawalError):
            withdrawals.cancel(player_id=other.id, req_id=rid)
        self.assertEqual(WithdrawalRequest.objects.get(pk=rid).status, 'requested')
