"""accounts tests — registration, auth, responsible gambling."""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.cache import cache
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
        cache.clear()  # signup is rate limited per IP; start each test with a clean slate
        self.client = APIClient()

    def test_register_creates_player_and_wallet(self):
        resp = self.client.post('/api/auth/register/', {
            'username': 'newuser', 'email': 'newuser@example.com', 'password': 'Str0ngPass!',
            'accept_terms': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(Player.objects.filter(username='newuser').exists())
        bal = wallet_services.get_balance(Player.objects.get(username='newuser').id)
        self.assertEqual(bal, Decimal('0.00'))

    def test_register_duplicate_username_fails(self):
        _make_player(username='dupuser', email='dup@example.com')
        resp = self.client.post('/api/auth/register/', {
            'username': 'dupuser', 'email': 'other@example.com', 'password': 'Str0ngPass!', 'accept_terms': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_duplicate_email_fails(self):
        _make_player(username='emailuser', email='same@example.com')
        resp = self.client.post('/api/auth/register/', {
            'username': 'emailuser2', 'email': 'same@example.com', 'password': 'Str0ngPass!', 'accept_terms': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


    def test_register_email_is_case_insensitive(self):
        _make_player(username='caseuser', email='case@example.com')
        resp = self.client.post('/api/auth/register/', {
            'username': 'caseuser2', 'email': 'CASE@Example.com', 'password': 'Str0ngPass!', 'accept_terms': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_register_conflicts_do_not_reveal_which_field(self):
        _make_player(username='takenuser', email='taken@example.com')
        by_name = self.client.post('/api/auth/register/', {
            'username': 'TakenUser', 'email': 'fresh@example.com', 'password': 'Str0ngPass!', 'accept_terms': True,
        }, format='json')
        by_email = self.client.post('/api/auth/register/', {
            'username': 'freshuser', 'email': 'taken@example.com', 'password': 'Str0ngPass!', 'accept_terms': True,
        }, format='json')
        self.assertEqual(by_name.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(by_name.data, by_email.data)
        self.assertEqual(set(by_name.data), {'non_field_errors'})

    def test_register_requires_terms_acceptance(self):
        base = {'username': 'termsuser', 'email': 'terms@example.com', 'password': 'Str0ngPass!'}
        for extra in ({}, {'accept_terms': False}):
            resp = self.client.post('/api/auth/register/', {**base, **extra}, format='json')
            self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
            self.assertIn('accept_terms', resp.data)
        self.assertFalse(Player.objects.filter(username='termsuser').exists())

    def test_register_reports_field_errors(self):
        resp = self.client.post('/api/auth/register/', {
            'username': '!!', 'email': 'f@example.com', 'password': '12345678', 'currency': 'ZZZ', 'accept_terms': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(resp.data), {'username', 'currency'})
        resp = self.client.post('/api/auth/register/', {
            'username': 'fielduser', 'email': 'f@example.com', 'password': '12345678', 'accept_terms': True,
        }, format='json')
        self.assertIn('password', resp.data)

    def test_register_with_unknown_referral_still_succeeds(self):
        resp = self.client.post('/api/auth/register/', {
            'username': 'refuser', 'email': 'ref@example.com', 'password': 'Str0ngPass!', 'ref': 'NOSUCHCODE',
            'accept_terms': True,
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(resp.data['username'], 'refuser')

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


class LoginIdentifierTests(TestCase):
    """The login form accepts "username or email" (sign-up logs in with the email)."""

    def test_login_with_email_or_any_case_username(self):
        from rest_framework.test import APIClient
        import secrets
        from apps.accounts import services as account_services
        password = secrets.token_urlsafe(16)  # generated per run; test-only
        account_services.register_player(username='Mixed_Case', email='mc@example.com', password=password)
        client = APIClient()
        for identifier in ('mixed_case', 'MIXED_CASE', 'mc@example.com', 'MC@Example.com'):
            res = client.post('/api/auth/login/', {'username': identifier, 'password': password}, format='json')
            self.assertEqual(res.status_code, 200, identifier)
        res = client.post('/api/auth/login/', {'username': 'mc@example.com', 'password': 'wrong'}, format='json')
        self.assertEqual(res.status_code, 401)
