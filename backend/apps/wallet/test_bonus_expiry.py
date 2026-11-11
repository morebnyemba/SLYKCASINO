"""An unused Bonus wallet expires after the admin's period (30 days by default),
with a warning 3 days before; using it, or a bonus ticket still open, keeps it."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from apps.notifications.models import Notification
from apps.sportsbook.models import BetSlip
from apps.wallet import bonus, services
from apps.wallet.models import LedgerEntry, WalletRules


class BonusExpiryTests(TestCase):
    def setUp(self):
        self.player = accounts.create_player(username='bonus_holder')
        services.credit(player_id=self.player.id, amount=D('25'), kind='bonus', idempotency_key='b1')
        self.now = timezone.now()

    def bonus_balance(self):
        return services.get_balances(self.player.id)['bonus']

    def at(self, days):
        return bonus.expire_idle(now=self.now + timedelta(days=days))

    def test_default_is_30_days(self):
        self.assertEqual(WalletRules.load().bonus_expiry_days, 30)

    def test_warns_three_days_before_then_expires_once(self):
        self.assertEqual(self.at(26)['warned'], 0)
        self.assertEqual(self.at(27.5)['warned'], 1)
        self.assertEqual(self.at(28)['warned'], 0)                       # one warning only
        self.assertTrue(Notification.objects.filter(player_id=self.player.id, title='Bonus expiring soon').exists())
        report = self.at(30.1)
        self.assertEqual((report['expired'], report['amount']), (1, D('25.00')))
        self.assertEqual(self.bonus_balance(), D('0.00'))
        self.assertEqual(LedgerEntry.objects.filter(kind='bonus_forfeit', reference='bonus-expired').count(), 1)
        self.assertEqual(self.at(31)['expired'], 0)                      # never twice
        self.assertTrue(Notification.objects.filter(player_id=self.player.id, title='Bonus expired').exists())

    def test_using_the_bonus_restarts_the_countdown(self):
        from unittest.mock import patch
        day20 = self.now + timedelta(days=20)
        with patch('django.utils.timezone.now', return_value=day20):     # the ledger is append-only: bet "on day 20"
            services.debit(player_id=self.player.id, amount=D('5'), kind='bet_stake', bucket='bonus', idempotency_key='s1')
        self.assertEqual(self.at(31)['expired'], 0)                      # used on day 20
        self.assertEqual(self.at(50.1)['expired'], 1)

    def test_an_open_bonus_ticket_keeps_it_alive(self):
        BetSlip.objects.create(wallet='bonus', player_id=self.player.id, stake=D('5'), combined_odds=D('60'), status='open')
        self.assertEqual(self.at(40)['expired'], 0)
        self.assertIsNone(bonus.expires_at(self.player.id))

    def test_zero_means_never(self):
        WalletRules.objects.filter(pk=WalletRules.load().pk).update(bonus_expiry_days=0)
        self.assertEqual(self.at(400)['expired'], 0)
        self.assertEqual(self.bonus_balance(), D('25.00'))

    def test_player_sees_when_it_expires(self):
        api = APIClient()
        user = User.objects.create_user('bh', 'bh@example.com', 'x')
        self.player.user = user
        self.player.save(update_fields=['user'])
        api.force_authenticate(user)
        expires = api.get('/api/wallet/').json()['wallets']['bonus']['expires_at']
        self.assertIsNotNone(expires)
        self.assertEqual(expires[:10], (LedgerEntry.objects.get(idempotency_key='b1').created_at + timedelta(days=30)).isoformat()[:10])

    def test_admin_sets_the_period(self):
        api = APIClient()
        api.force_authenticate(User.objects.create_superuser('ops', 'o@example.com', 'x'))
        self.assertEqual(api.put('/api/admin/wallet-rules/', {'bonus_expiry_days': 7}, format='json').json()['bonus_expiry_days'], 7)
        self.assertEqual(api.put('/api/admin/wallet-rules/', {'bonus_expiry_days': 366}, format='json').status_code, 400)
        self.assertEqual(self.at(7.1)['expired'], 1)
