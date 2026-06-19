"""casino tests — game listing, round lifecycle."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from django.utils import timezone

from apps.accounts import services as account_services
from apps.casino import crash_engine, services as casino_services
from apps.casino.models import CrashRound, Game, GameRound
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


class CrashEngineTests(TestCase):
    def test_crash_point_in_range_and_deterministic(self):
        seed = crash_engine.new_server_seed()
        first = crash_engine.crash_point(seed, 7)
        self.assertGreaterEqual(first, Decimal('1.00'))
        self.assertEqual(first, crash_engine.crash_point(seed, 7))  # deterministic

    def test_seed_hash_matches_commitment(self):
        import hashlib
        seed = crash_engine.new_server_seed()
        self.assertEqual(crash_engine.seed_hash(seed), hashlib.sha256(seed.encode()).hexdigest())

    def test_multiplier_rises_with_time(self):
        self.assertEqual(crash_engine.multiplier_at(0), Decimal('1.00'))
        self.assertGreater(crash_engine.multiplier_at(5), crash_engine.multiplier_at(2))


class CrashApiTests(TestCase):
    def setUp(self):
        self.player = _make_player(username='crashp', email='crash@example.com')
        refresh = RefreshToken.for_user(self.player.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

    def _backdate(self, crash_id, *, seconds, crash_point):
        """Pin a round's start time and crash point so cash-out is deterministic."""
        CrashRound.objects.filter(pk=crash_id).update(
            created_at=timezone.now() - timezone.timedelta(seconds=seconds),
            crash_point=Decimal(crash_point),
        )

    def test_bet_debits_and_hides_crash_point(self):
        before = wallet_services.get_balance(self.player.id)
        resp = self.client.post('/api/casino/crash/', {'stake': '20.00'}, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertEqual(wallet_services.get_balance(self.player.id), before - Decimal('20.00'))
        self.assertIsNone(resp.data['crash_point'])   # hidden while running
        self.assertIsNone(resp.data['server_seed'])   # seed not revealed yet

    def test_cashout_below_crash_point_wins(self):
        resp = self.client.post('/api/casino/crash/', {'stake': '10.00'}, format='json')
        crash_id = resp.data['id']
        self._backdate(crash_id, seconds=2, crash_point='100.00')  # current ~1.34x, no bust
        after_bet = wallet_services.get_balance(self.player.id)

        out = self.client.post(f'/api/casino/crash/{crash_id}/cashout/', {'multiplier': '1.20'}, format='json')
        self.assertEqual(out.status_code, status.HTTP_200_OK)
        self.assertEqual(out.data['round']['status'], 'cashed')
        self.assertEqual(Decimal(out.data['round']['win']), Decimal('12.00'))  # 10 * 1.20
        self.assertEqual(wallet_services.get_balance(self.player.id), after_bet + Decimal('12.00'))
        self.assertIsNotNone(out.data['round']['server_seed'])  # revealed after settle

    def test_cashout_at_or_above_crash_point_busts(self):
        resp = self.client.post('/api/casino/crash/', {'stake': '10.00'}, format='json')
        crash_id = resp.data['id']
        self._backdate(crash_id, seconds=5, crash_point='1.00')  # already crashed
        out = self.client.post(f'/api/casino/crash/{crash_id}/cashout/', {'multiplier': '1.50'}, format='json')
        self.assertEqual(out.data['round']['status'], 'busted')
        self.assertEqual(Decimal(out.data['round']['win']), Decimal('0'))

    def test_cashout_is_idempotent(self):
        resp = self.client.post('/api/casino/crash/', {'stake': '10.00'}, format='json')
        crash_id = resp.data['id']
        self._backdate(crash_id, seconds=2, crash_point='100.00')
        self.client.post(f'/api/casino/crash/{crash_id}/cashout/', {'multiplier': '1.20'}, format='json')
        balance_after_first = wallet_services.get_balance(self.player.id)
        # A second cash-out must not pay again.
        self.client.post(f'/api/casino/crash/{crash_id}/cashout/', {'multiplier': '1.20'}, format='json')
        self.assertEqual(wallet_services.get_balance(self.player.id), balance_after_first)
