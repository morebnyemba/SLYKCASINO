"""accounts tests — registration, auth, responsible gambling."""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services as account_services
from apps.accounts.models import Player
from apps.wallet import services as wallet_services

User = get_user_model()


def _make_player(username='testplayer', email='test@example.com', password='Passw0rd!', balance=Decimal('1000.00')):
    """Helper: create user + player + wallet."""
    player = account_services.register_player(
        username=username, email=email, password=password, currency='USD',
    )
    if balance > 0:
        wallet_services.credit(
            player_id=player.id, amount=balance, kind='deposit',
            idempotency_key=f'setup:deposit:{player.id}',
        )
    return player


class RegisterTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_register_creates_player_and_wallet(self):
        resp = self.client.post('/api/auth/register/', {
            'username': 'newuser', 'email': 'newuser@example.com', 'password': 'Str0ngPass!',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Player.objects.filter(username='newuser').exists())
        bal = wallet_services.get_balance(Player.objects.get(username='newuser').id)
        self.assertEqual(bal, Decimal('0.00'))

    def test_register_duplicate_username_fails(self):
        _make_player(username='dupuser', email='dup@example.com')
        resp = self.client.post('/api/auth/register/', {
            'username': 'dupuser', 'email': 'other@example.com', 'password': 'Str0ngPass!',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_duplicate_email_fails(self):
        _make_player(username='emailuser', email='same@example.com')
        resp = self.client.post('/api/auth/register/', {
            'username': 'emailuser2', 'email': 'same@example.com', 'password': 'Str0ngPass!',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class LoginLogoutTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.player = _make_player()

    def test_login_returns_tokens(self):
        resp = self.client.post('/api/auth/login/', {
            'username': 'testplayer', 'password': 'Passw0rd!',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertIn('access', resp.data)
        self.assertIn('refresh', resp.data)

    def test_logout_blacklists_token(self):
        login = self.client.post('/api/auth/login/', {
            'username': 'testplayer', 'password': 'Passw0rd!',
        }, format='json')
        access = login.data['access']
        refresh = login.data['refresh']

        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {access}')
        resp = self.client.post('/api/auth/logout/', {'refresh': refresh}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_204_NO_CONTENT)

        # Using the same refresh token again should fail (blacklisted).
        resp2 = self.client.post('/api/auth/refresh/', {'refresh': refresh}, format='json')
        self.assertNotEqual(resp2.status_code, status.HTTP_200_OK)


class PlayerMeTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.player = _make_player()
        refresh = RefreshToken.for_user(self.player.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

    def test_me_endpoint_returns_player(self):
        resp = self.client.get('/api/players/me/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['username'], 'testplayer')


class ResponsibleGamblingTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.player = _make_player()
        refresh = RefreshToken.for_user(self.player.user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

    def test_set_deposit_limit(self):
        resp = self.client.patch('/api/players/me/rg/', {'deposit_limit_daily': '50.00'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data['deposit_limit_daily'], '50.00')

    def test_deposit_limit_enforced(self):
        account_services.set_deposit_limit(self.player.id, '50.00')
        resp = self.client.post('/api/wallet/deposit/', {'amount': '100.00'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_self_exclude_blocks_deposit(self):
        account_services.self_exclude(self.player.id)
        resp = self.client.post('/api/wallet/deposit/', {'amount': '10.00'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)
