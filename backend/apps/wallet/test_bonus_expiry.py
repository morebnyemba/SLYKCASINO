"""An unused Bonus wallet expires after the admin's period — 72 hours by default,
15 days at most — with a warning 24 hours before; using it, or a bonus ticket
still open, keeps it. Bonuses already unused at deploy get a full period."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal as D
from unittest.mock import patch

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
        # Expiry introduced well before this bonus, so its own last use counts.
        WalletRules.objects.filter(pk=WalletRules.load().pk).update(bonus_expiry_from=timezone.now() - timedelta(days=60))
        self.player = accounts.create_player(username='bonus_holder')
        services.credit(player_id=self.player.id, amount=D('25'), kind='bonus', idempotency_key='b1')
        self.now = timezone.now()

    def bonus_balance(self):
        return services.get_balances(self.player.id)['bonus']

    def at(self, hours):
        return bonus.expire_idle(now=self.now + timedelta(hours=hours))

    def set_hours(self, hours):
        WalletRules.objects.filter(pk=WalletRules.load().pk).update(bonus_expiry_hours=hours)

    def test_default_is_72_hours(self):
        self.assertEqual(WalletRules.load().bonus_expiry_hours, 72)

    def test_warns_24_hours_before_then_expires_once(self):
        self.assertEqual(self.at(47)['warned'], 0)
        self.assertEqual(self.at(49)['warned'], 1)
        self.assertEqual(self.at(60)['warned'], 0)                      # one warning only
        report = self.at(72.1)
        self.assertEqual((report['expired'], report['amount']), (1, D('25.00')))
        self.assertEqual(self.bonus_balance(), D('0.00'))
        self.assertEqual(LedgerEntry.objects.filter(kind='bonus_forfeit', reference='bonus-expired').count(), 1)
        self.assertEqual(self.at(100)['expired'], 0)                    # never twice
        self.assertTrue(Notification.objects.filter(player_id=self.player.id, title='Bonus expired',
                                                    body__contains='after 72 hours').exists())

    def test_five_days_and_fifteen_days(self):
        self.set_hours(120)
        self.assertEqual(self.at(119)['expired'], 0)
        self.set_hours(360)
        self.assertEqual(self.at(359)['expired'], 0)
        self.assertEqual(self.at(360.1)['expired'], 1)
        self.assertTrue(Notification.objects.filter(title='Bonus expired', body__contains='after 15 days').exists())

    def test_using_the_bonus_restarts_the_countdown(self):
        with patch('django.utils.timezone.now', return_value=self.now + timedelta(hours=60)):   # append-only ledger
            services.debit(player_id=self.player.id, amount=D('5'), kind='bet_stake', bucket='bonus', idempotency_key='s1')
        self.assertEqual(self.at(73)['expired'], 0)                     # used at hour 60
        self.assertEqual(self.at(132.1)['expired'], 1)

    def test_an_open_bonus_ticket_keeps_it_alive(self):
        BetSlip.objects.create(wallet='bonus', player_id=self.player.id, stake=D('5'), combined_odds=D('60'), status='open')
        self.assertEqual(self.at(400)['expired'], 0)
        self.assertIsNone(bonus.expires_at(self.player.id))

    def test_bonuses_unused_at_deploy_get_a_full_period_from_the_deploy(self):
        deploy = self.now + timedelta(hours=100)                        # the bonus was already 100 hours old
        WalletRules.objects.filter(pk=WalletRules.load().pk).update(bonus_expiry_from=deploy)
        self.assertEqual(self.at(101)['expired'], 0)
        self.assertEqual(self.at(171)['expired'], 0)
        self.assertEqual(self.at(172.1)['expired'], 1)

    def test_player_sees_when_it_expires(self):
        api = APIClient()
        user = User.objects.create_user('bh', 'bh@example.com', 'x')
        self.player.user = user
        self.player.save(update_fields=['user'])
        api.force_authenticate(user)
        expires = api.get('/api/wallet/').json()['wallets']['bonus']['expires_at']
        credited = LedgerEntry.objects.get(idempotency_key='b1').created_at
        self.assertEqual(expires[:16], (credited + timedelta(hours=72)).isoformat()[:16])

    def test_admin_sets_the_period_within_24_hours_and_15_days(self):
        api = APIClient()
        api.force_authenticate(User.objects.create_superuser('ops', 'o@example.com', 'x'))
        self.assertEqual(api.put('/api/admin/wallet-rules/', {'bonus_expiry_hours': 120}, format='json').json()['bonus_expiry_hours'], 120)
        for bad in (0, 23, 361):
            self.assertEqual(api.put('/api/admin/wallet-rules/', {'bonus_expiry_hours': bad}, format='json').status_code, 400, bad)
