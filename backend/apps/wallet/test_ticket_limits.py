"""Stake and selection limits on every sportsbook ticket, and the Deposit
wallet's 1.50 minimum odds — all set by staff and applied on the next bet."""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts import services as account_services
from apps.sportsbook import services as sb
from apps.wallet import services
from apps.wallet.models import WalletRules

D = Decimal
pytestmark = pytest.mark.wallet_rules


def legs(n, odds='1.50'):
    return [{'event': f'Match {i}', 'odds': D(odds)} for i in range(n)]


class TicketLimitTests(TestCase):
    def setUp(self):
        self.player = account_services.create_player(username='limits_player')
        services.credit(player_id=self.player.id, amount=D('5000'), kind='deposit', idempotency_key='d1')
        services.credit(player_id=self.player.id, amount=D('2000'), kind='bonus', idempotency_key='b1')
        self.staff = APIClient()
        self.staff.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))

    def single(self, stake, odds='2.00'):
        return sb.place_bet(event='A v B', stake=D(stake), odds=D(odds), player_id=self.player.id, wallet='deposit')

    def test_defaults(self):
        rules = WalletRules.load()
        self.assertEqual((rules.min_stake, rules.max_stake, rules.max_selections, rules.deposit_min_odds),
                         (D('0.50'), D('1000.00'), 15, D('1.50')))

    def test_stake_must_be_within_the_limits(self):
        with self.assertRaisesMessage(services.WalletRuleError, 'minimum stake is $0.50'):
            self.single('0.49')
        with self.assertRaisesMessage(services.WalletRuleError, 'maximum stake is $1000.00'):
            self.single('1000.01')
        self.single('0.50')
        self.single('1000')

    def test_at_most_fifteen_selections(self):
        sb.place_accumulator(stake=D('5'), legs=legs(15), player_id=self.player.id, wallet='deposit')
        with self.assertRaisesMessage(services.WalletRuleError, 'at most 15 selections'):
            sb.place_accumulator(stake=D('5'), legs=legs(16), player_id=self.player.id, wallet='deposit')

    def test_deposit_wallet_needs_combined_odds_of_1_50(self):
        with self.assertRaises(services.WalletRuleError):
            self.single('5', odds='1.49')
        self.single('5', odds='1.50')

    def test_bonus_tickets_stake_the_whole_wallet_whatever_the_stake_limits(self):
        slip = sb.place_accumulator(stake=D('2000'), legs=legs(10), player_id=self.player.id, wallet='bonus')
        self.assertEqual(slip.stake, D('2000.00'))

    def test_staff_changes_apply_to_the_next_bet_and_the_slip(self):
        res = self.staff.put('/api/admin/wallet-rules/', {'min_stake': '2', 'max_stake': '50', 'max_selections': 12},
                             format='json')
        self.assertEqual(res.status_code, 200, res.content)
        with self.assertRaises(services.WalletRuleError):
            self.single('1.99')
        with self.assertRaises(services.WalletRuleError):
            self.single('50.01')
        with self.assertRaises(services.WalletRuleError):
            sb.place_accumulator(stake=D('5'), legs=legs(13), player_id=self.player.id, wallet='deposit')
        limits = APIClient().get('/api/multibet-bonus/').json()['limits']
        self.assertEqual(limits, {'min_stake': '2.00', 'max_stake': '50.00', 'max_selections': 12})

    def test_staff_cannot_save_impossible_limits(self):
        for body in ({'min_stake': '0'}, {'min_stake': '20', 'max_stake': '10'}, {'max_selections': 1},
                     {'max_selections': 9}):  # bonus tickets need 10
            self.assertEqual(self.staff.put('/api/admin/wallet-rules/', body, format='json').status_code, 400, body)

    def test_placement_api_reports_the_limit(self):
        import secrets

        from rest_framework_simplejwt.tokens import RefreshToken
        punter = account_services.register_player(username='api_punter', email='p@example.com',
                                                  password=secrets.token_urlsafe(16), currency='USD')
        services.credit(player_id=punter.id, amount=D('50'), kind='deposit', idempotency_key='api:d1')
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(punter.user).access_token}')
        res = api.post('/api/bets/', {'event': 'A v B', 'stake': '0.10', 'odds': '2.00', 'wallet': 'deposit'},
                       format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('minimum stake', res.json()['detail'])
