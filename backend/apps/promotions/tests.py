"""promotions tests — listing, claiming, duplicate prevention."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from django.utils import timezone

from apps.accounts import services as account_services
from apps.promotions import services as promo_services
from apps.promotions.models import Promotion, PromotionClaim, Tournament, TournamentEntry
from apps.wallet import services as wallet_services


def _make_player(username='promoplayer', email='promo@example.com'):
    player = account_services.register_player(
        username=username, email=email, password='Passw0rd!', currency='USD',
    )
    wallet_services.credit(
        player_id=player.id, amount=Decimal('1000.00'),
        kind='deposit', idempotency_key=f'setup:promo:{player.id}',
    )
    return player


def _make_promotion(name='Welcome Bonus', bonus=Decimal('50.00')):
    return Promotion.objects.create(
        name=name, kind=Promotion.Kind.DEPOSIT,
        active=True, bonus_amount=bonus, wagering_multiplier=Decimal('5.00'),
    )


class PromotionListTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        _make_promotion()

    def test_promotions_public(self):
        resp = self.client.get('/api/promotions/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(resp.data), 1)


class PromotionClaimTests(TestCase):
    def setUp(self):
        self.player = _make_player()
        self.promo = _make_promotion()
        refresh = RefreshToken.for_user(self.player.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

    def test_claim_promotion(self):
        resp = self.client.post(f'/api/promotions/{self.promo.id}/claim/')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            PromotionClaim.objects.filter(
                player_id=self.player.id, promotion=self.promo,
            ).exists()
        )

    def test_claim_credits_bonus_to_wallet(self):
        before = wallet_services.get_balance(self.player.id)
        self.client.post(f'/api/promotions/{self.promo.id}/claim/')
        after = wallet_services.get_balance(self.player.id)
        self.assertEqual(after - before, self.promo.bonus_amount)

    def test_cannot_claim_twice(self):
        self.client.post(f'/api/promotions/{self.promo.id}/claim/')
        resp2 = self.client.post(f'/api/promotions/{self.promo.id}/claim/')
        # Second claim returns 201 (idempotent — same claim returned) but only one claim exists
        count = PromotionClaim.objects.filter(
            player_id=self.player.id, promotion=self.promo,
        ).count()
        self.assertEqual(count, 1)

    def test_claim_requires_auth(self):
        anon = APIClient()
        resp = anon.post(f'/api/promotions/{self.promo.id}/claim/')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)


def _make_tournament(name='Weekly Race', *, live=True):
    now = timezone.now()
    return Tournament.objects.create(
        name=name, metric=Tournament.Metric.WAGERED, prize_pool=Decimal('500.00'),
        active=True,
        starts_at=now - timezone.timedelta(days=1) if live else now + timezone.timedelta(days=1),
        ends_at=now + timezone.timedelta(days=5),
    )


class TournamentTests(TestCase):
    def setUp(self):
        self.player = _make_player(username='tplayer', email='t@example.com')
        self.tournament = _make_tournament()
        refresh = RefreshToken.for_user(self.player.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

    def test_list_public(self):
        resp = APIClient().get('/api/promotions/tournaments/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(resp.data), 1)

    def test_join_creates_entry(self):
        resp = self.client.post(f'/api/promotions/tournaments/{self.tournament.id}/join/')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        self.assertTrue(
            TournamentEntry.objects.filter(tournament=self.tournament, player_id=self.player.id).exists()
        )

    def test_join_is_idempotent(self):
        self.client.post(f'/api/promotions/tournaments/{self.tournament.id}/join/')
        self.client.post(f'/api/promotions/tournaments/{self.tournament.id}/join/')
        count = TournamentEntry.objects.filter(tournament=self.tournament, player_id=self.player.id).count()
        self.assertEqual(count, 1)

    def test_cannot_join_when_not_live(self):
        upcoming = _make_tournament(name='Upcoming', live=False)
        resp = self.client.post(f'/api/promotions/tournaments/{upcoming.id}/join/')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)

    def test_record_play_scores_only_joined_players(self):
        promo_services.join_tournament(
            player_id=self.player.id, player_name=self.player.username, tournament_id=self.tournament.id,
        )
        promo_services.record_tournament_play(player_id=self.player.id, wagered=Decimal('30.00'))
        promo_services.record_tournament_play(player_id=self.player.id, wagered=Decimal('20.00'))
        entry = TournamentEntry.objects.get(tournament=self.tournament, player_id=self.player.id)
        self.assertEqual(entry.score, Decimal('50.00'))

    def test_leaderboard_ordered_by_score(self):
        other = _make_player(username='tplayer2', email='t2@example.com')
        for p, wager in ((self.player, '10.00'), (other, '40.00')):
            promo_services.join_tournament(player_id=p.id, player_name=p.username, tournament_id=self.tournament.id)
            promo_services.record_tournament_play(player_id=p.id, wagered=Decimal(wager))
        resp = APIClient().get(f'/api/promotions/tournaments/{self.tournament.id}/leaderboard/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertEqual(resp.data[0]['player_name'], 'tplayer2')  # highest score first
