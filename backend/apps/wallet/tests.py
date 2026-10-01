"""wallet tests — deposits, withdrawals, ledger idempotency."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services as account_services
from apps.wallet import services as wallet_services
from apps.wallet.models import LedgerEntry


def _make_player(username='walletplayer', email='wallet@example.com'):
    player = account_services.register_player(
        username=username, email=email, password='Passw0rd!', currency='USD',
    )
    return player


class WalletServiceTests(TestCase):
    def setUp(self):
        self.player = _make_player()

    def test_deposit_credits_balance(self):
        wallet_services.credit(
            player_id=self.player.id, amount=Decimal('100.00'),
            kind='deposit', idempotency_key='test:dep:1',
        )
        self.assertEqual(wallet_services.get_balance(self.player.id), Decimal('100.00'))

    def test_withdraw_debits_balance(self):
        wallet_services.credit(
            player_id=self.player.id, amount=Decimal('100.00'),
            kind='deposit', idempotency_key='test:dep:2',
        )
        wallet_services.debit(
            player_id=self.player.id, amount=Decimal('50.00'),
            kind='withdrawal', idempotency_key='test:wdraw:2',
        )
        self.assertEqual(wallet_services.get_balance(self.player.id), Decimal('50.00'))

    def test_withdraw_insufficient_funds(self):
        from apps.wallet.services import InsufficientFunds
        with self.assertRaises(InsufficientFunds):
            wallet_services.debit(
                player_id=self.player.id, amount=Decimal('500.00'),
                kind='withdrawal', idempotency_key='test:wdraw:3',
            )

    def test_ledger_entry_created_on_deposit(self):
        before = LedgerEntry.objects.filter(wallet__player_id=self.player.id).count()
        wallet_services.credit(
            player_id=self.player.id, amount=Decimal('75.00'),
            kind='deposit', idempotency_key='test:dep:ledger',
        )
        after = LedgerEntry.objects.filter(wallet__player_id=self.player.id).count()
        self.assertEqual(after, before + 1)

    def test_idempotent_deposit(self):
        wallet_services.credit(
            player_id=self.player.id, amount=Decimal('50.00'),
            kind='deposit', idempotency_key='test:dep:idem',
        )
        wallet_services.credit(
            player_id=self.player.id, amount=Decimal('50.00'),
            kind='deposit', idempotency_key='test:dep:idem',
        )
        count = LedgerEntry.objects.filter(
            wallet__player_id=self.player.id, idempotency_key='test:dep:idem',
        ).count()
        self.assertEqual(count, 1)
        self.assertEqual(wallet_services.get_balance(self.player.id), Decimal('50.00'))


class WalletAPITests(TestCase):
    def setUp(self):
        self.player = _make_player()
        # Withdrawals require KYC verification; deposits don't.
        self.player.kyc_status = self.player.Kyc.VERIFIED
        self.player.save(update_fields=['kyc_status'])
        refresh = RefreshToken.for_user(self.player.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')
        # Seed with balance
        wallet_services.credit(
            player_id=self.player.id, amount=Decimal('1000.00'),
            kind='deposit', idempotency_key=f'setup:wallet:{self.player.id}',
        )

    def test_deposit_via_api_credits_balance(self):
        resp = self.client.post('/api/wallet/deposit/', {'amount': '200.00'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(resp.data['balance']), Decimal('1200.00'))

    def test_withdraw_via_api_debits_balance(self):
        resp = self.client.post('/api/wallet/withdraw/', {'amount': '100.00'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(Decimal(resp.data['balance']), Decimal('900.00'))

    def test_withdraw_insufficient_funds_returns_402(self):
        resp = self.client.post('/api/wallet/withdraw/', {'amount': '9999.00'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_402_PAYMENT_REQUIRED)

    def test_withdraw_requires_kyc_verification(self):
        self.player.kyc_status = self.player.Kyc.PENDING
        self.player.save(update_fields=['kyc_status'])
        resp = self.client.post('/api/wallet/withdraw/', {'amount': '50.00'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)


class PSPWebhookViewTests(TestCase):
    def setUp(self):
        self.player = _make_player(username='webhookplayer', email='webhook@example.com')
        self.client = APIClient()

    def test_unknown_provider_returns_404(self):
        resp = self.client.post('/api/wallet/webhook/nope/', data=b'{}', content_type='application/json')
        self.assertEqual(resp.status_code, status.HTTP_404_NOT_FOUND)

    def test_stub_provider_webhook_is_rejected(self):
        # StubPSP doesn't implement verify_webhook — an unverifiable payload
        # must never be trusted into a credit.
        resp = self.client.post('/api/wallet/webhook/stub/', data=b'{}', content_type='application/json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(wallet_services.get_balance(self.player.id), Decimal('0.00'))
