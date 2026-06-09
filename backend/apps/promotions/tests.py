"""promotions tests — listing, claiming, duplicate prevention."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services as account_services
from apps.promotions.models import Promotion, PromotionClaim
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
