"""Paynow deposits: signing, starting a payment, and crediting exactly once
from a verified callback or poll — never from a forged or mismatched one."""
from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch
from urllib.parse import parse_qsl, urlencode

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts import services as account_services
from apps.wallet import paynow, payments
from apps.wallet import services as wallet_services
from apps.wallet.models import LedgerEntry, PaymentTransaction

D = Decimal
KEY = 'test-integration-key'
PAYNOW = override_settings(
    PSP_PROVIDER='paynow', PAYNOW_INTEGRATION_ID='1201', PAYNOW_INTEGRATION_KEY=KEY,
    PAYNOW_AUTH_EMAIL='merchant@example.com', FRONTEND_URL='https://betblits.test',
)


def signed(fields: list[tuple[str, str]], key: str = KEY) -> str:
    return urlencode(paynow.sign(fields, key))


class _FakeResponse:
    def __init__(self, text):
        self.text = text
        self.status_code = 200


def _player(username):
    player = account_services.create_player(username=username)
    user = User.objects.create(username=username)
    user.set_unusable_password()
    user.save()
    player.user = user
    player.save(update_fields=['user'])
    return player, user


class SigningTests(TestCase):
    def test_round_trip_and_tamper_detection(self):
        body = signed([('reference', 'DEP1'), ('amount', '10.00'), ('status', 'Paid')])
        self.assertEqual(paynow.parse_signed(body, KEY)['status'], 'Paid')
        tampered = body.replace('10.00', '99.00')
        with self.assertRaises(paynow.PaynowError):
            paynow.parse_signed(tampered, KEY)
        with self.assertRaises(paynow.PaynowError):
            paynow.parse_signed(signed([('reference', 'DEP1')], 'wrong-key'), KEY)

    def test_error_reply_raises_with_message(self):
        with self.assertRaisesMessage(paynow.PaynowError, 'Invalid amount'):
            paynow.parse_signed('status=Error&error=Invalid+amount', KEY)

    def test_phone_normalisation(self):
        self.assertEqual(paynow.normalise_phone('+263 77 123 4567'), '0771234567')
        self.assertEqual(paynow.normalise_phone('771234567'), '0771234567')
        self.assertEqual(paynow.normalise_phone('0712 345 678'), '0712345678')
        with self.assertRaises(ValueError):
            paynow.normalise_phone('12345')


@PAYNOW
class PaynowDepositTests(TestCase):
    def setUp(self):
        self.player, self.user = _player('paynow_punter')
        self.api = APIClient()
        self.api.force_authenticate(self.user)

    def _start(self, method='ecocash', amount='25', phone='0771234567'):
        reply = signed([
            ('status', 'Ok'), ('instructions', 'Dial *151*2*4# and enter your PIN'),
            ('paynowreference', '998877'), ('pollurl', 'https://www.paynow.co.zw/interface/checkpayment/?guid=abc'),
        ])
        with patch('apps.wallet.paynow.requests.post', return_value=_FakeResponse(reply)) as post:
            res = self.api.post('/api/wallet/deposit/', {'amount': amount, 'method': method, 'phone': phone}, format='json')
        return res, post

    def _result(self, txn, status='Paid', amount=None):
        return signed([
            ('reference', txn.reference), ('amount', amount or f'{txn.amount:.2f}'),
            ('paynowreference', '998877'), ('pollurl', txn.poll_url), ('status', status),
        ])

    def test_start_sends_a_signed_express_checkout_and_does_not_credit(self):
        res, post = self._start()
        self.assertEqual(res.status_code, 202, res.content)
        body = res.json()
        self.assertEqual((body['status'], body['method']), ('pending', 'ecocash'))
        self.assertIn('*151*', body['instructions'])
        sent = parse_qsl(post.call_args.kwargs['data'])
        self.assertEqual(post.call_args.args[0], paynow.REMOTE_URL)
        sent_fields = dict(sent)
        self.assertEqual((sent_fields['method'], sent_fields['phone'], sent_fields['amount']), ('ecocash', '0771234567', '25.00'))
        self.assertEqual(sent_fields['resulturl'], 'https://betblits.test/api/wallet/paynow/result/')
        self.assertEqual(sent_fields['hash'], paynow.make_hash((v for k, v in sent if k != 'hash'), KEY))
        self.assertEqual(wallet_services.get_balance(self.player.id), D('0'))

    def test_verified_callback_credits_once(self):
        self._start()
        txn = PaymentTransaction.objects.get()
        result = self._result(txn)
        for _ in range(2):  # Paynow redelivers
            res = APIClient().post('/api/wallet/paynow/result/', result, content_type='application/x-www-form-urlencoded')
            self.assertEqual(res.status_code, 200)
        txn.refresh_from_db()
        self.assertEqual(txn.status, 'paid')
        self.assertEqual(wallet_services.get_balance(self.player.id), D('25.00'))
        self.assertEqual(LedgerEntry.objects.filter(kind='deposit').count(), 1)

    def test_forged_callback_is_rejected(self):
        self._start()
        txn = PaymentTransaction.objects.get()
        forged = self._result(txn).replace('hash=', 'hash=00')
        res = APIClient().post('/api/wallet/paynow/result/', forged, content_type='application/x-www-form-urlencoded')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(wallet_services.get_balance(self.player.id), D('0'))

    def test_amount_mismatch_never_credits(self):
        self._start()
        txn = PaymentTransaction.objects.get()
        payments.handle_result(self._result(txn, amount='2.50').encode())
        txn.refresh_from_db()
        self.assertEqual(txn.status, 'failed')
        self.assertEqual(wallet_services.get_balance(self.player.id), D('0'))

    def test_status_poll_credits_when_paid(self):
        self._start()
        txn = PaymentTransaction.objects.get()
        with patch('apps.wallet.paynow.requests.post', return_value=_FakeResponse(self._result(txn))):
            PaymentTransaction.objects.filter(pk=txn.pk).update(updated_at=txn.created_at.replace(year=2000))
            res = self.api.get(f'/api/wallet/deposits/{txn.reference}/')
        self.assertEqual(res.json()['status'], 'paid')
        self.assertEqual(res.json()['balance'], '25.00')

    def test_cancelled_payment_is_final(self):
        self._start()
        txn = PaymentTransaction.objects.get()
        payments.handle_result(self._result(txn, status='Cancelled').encode())
        payments.handle_result(self._result(txn).encode())  # a late "Paid" can't revive it
        txn.refresh_from_db()
        self.assertEqual(txn.status, 'cancelled')
        self.assertEqual(wallet_services.get_balance(self.player.id), D('0'))

    def test_card_returns_redirect(self):
        reply = signed([('status', 'Ok'), ('browserurl', 'https://www.paynow.co.zw/Payment/ConfirmPayment/1'),
                        ('pollurl', 'https://www.paynow.co.zw/interface/checkpayment/?guid=x')])
        with patch('apps.wallet.paynow.requests.post', return_value=_FakeResponse(reply)) as post:
            res = self.api.post('/api/wallet/deposit/', {'amount': '40', 'method': 'card'}, format='json')
        self.assertEqual(post.call_args.args[0], paynow.INITIATE_URL)
        self.assertEqual(res.json()['redirect_url'], 'https://www.paynow.co.zw/Payment/ConfirmPayment/1')

    def test_bad_phone_and_unknown_method(self):
        res, _ = self._start(phone='123')
        self.assertEqual(res.status_code, 400)
        res, _ = self._start(method='usdt')
        self.assertEqual(res.status_code, 400)

    def test_paynow_refusal_marks_failed(self):
        with patch('apps.wallet.paynow.requests.post', return_value=_FakeResponse('status=Error&error=Insufficient+balance')):
            res = self.api.post('/api/wallet/deposit/', {'amount': '25', 'method': 'ecocash', 'phone': '0771234567'}, format='json')
        self.assertEqual(res.status_code, 502)
        self.assertEqual(PaymentTransaction.objects.get().status, 'failed')

    def test_other_players_cannot_read_a_deposit(self):
        self._start()
        txn = PaymentTransaction.objects.get()
        _, other = _player('nosy_punter')
        api = APIClient()
        api.force_authenticate(other)
        self.assertEqual(api.get(f'/api/wallet/deposits/{txn.reference}/').status_code, 404)

    def test_wallet_lists_gateway_methods(self):
        self.assertEqual(self.api.get('/api/wallet/').json()['deposit_methods'], ['ecocash', 'onemoney', 'innbucks', 'card'])
