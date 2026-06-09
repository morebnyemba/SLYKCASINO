"""casino tests — game listing, round lifecycle."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services as account_services
from apps.casino.models import Game, GameRound
from apps.wallet import services as wallet_services


def _make_player(username='casinoplayer', email='casino@example.com'):
    player = account_services.register_player(
        username=username, email=email, password='Passw0rd!', currency='USD',
    )
    wallet_services.credit(
        player_id=player.id, amount=Decimal('1000.00'),
        kind='deposit', idempotency_key=f'setup:casino:{player.id}',
    )
    return player


def _make_game(slug='slots-test', name='Test Slots'):
    return Game.objects.create(slug=slug, name=name, provider='stub', is_active=True)


class GameListTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        _make_game()

    def test_game_list_public(self):
        resp = self.client.get('/api/casino/games/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(resp.data), 1)


class CasinoPlayTests(TestCase):
    def setUp(self):
        self.player = _make_player()
        self.game = _make_game()
        refresh = RefreshToken.for_user(self.player.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

    def test_play_requires_auth(self):
        anon = APIClient()
        resp = anon.post(f'/api/casino/games/{self.game.id}/play/', {'stake': '10.00'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_play_debits_stake(self):
        before = wallet_services.get_balance(self.player.id)
        resp = self.client.post(
            f'/api/casino/games/{self.game.id}/play/', {'stake': '50.00'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        after = wallet_services.get_balance(self.player.id)
        # Stake was debited; net balance = before - stake + win
        stake = Decimal('50.00')
        win = Decimal(resp.data['win'])
        self.assertEqual(after, before - stake + win)

    def test_round_created(self):
        before = GameRound.objects.filter(player_id=self.player.id).count()
        self.client.post(
            f'/api/casino/games/{self.game.id}/play/', {'stake': '10.00'}, format='json',
        )
        after = GameRound.objects.filter(player_id=self.player.id).count()
        self.assertEqual(after, before + 1)

    def test_round_settled_after_play(self):
        resp = self.client.post(
            f'/api/casino/games/{self.game.id}/play/', {'stake': '10.00'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        round_id = resp.data['round']['id']
        rnd = GameRound.objects.get(pk=round_id)
        self.assertEqual(rnd.status, GameRound.Status.SETTLED)

    def test_play_insufficient_funds_returns_402(self):
        resp = self.client.post(
            f'/api/casino/games/{self.game.id}/play/', {'stake': '9999.00'}, format='json',
        )
        self.assertEqual(resp.status_code, status.HTTP_402_PAYMENT_REQUIRED)
