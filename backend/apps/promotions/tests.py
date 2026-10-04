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


class BannerPlacementTests(TestCase):
    """Each surface (homepage, sportsbook) asks for its own live banners."""

    def test_placement_filter(self):
        from apps.promotions.models import Banner
        Banner.objects.create(title='Home promo', image_url='https://x/h.jpg', placement='home_hero')
        Banner.objects.create(title='Acca boost', image_url='https://x/s.jpg', placement='sportsbook')
        Banner.objects.create(title='Hidden', image_url='https://x/o.jpg', placement='sportsbook', active=False)

        def titles(query):
            data = APIClient().get(f'/api/promotions/banners/{query}').json()
            return sorted(b['title'] for b in data.get('results', data))

        self.assertEqual(titles('?placement=sportsbook'), ['Acca boost'])
        self.assertEqual(titles('?placement=home_hero'), ['Home promo'])
        self.assertEqual(titles(''), ['Acca boost', 'Home promo'])


class DemoBannerMigrationTests(TestCase):
    def test_removes_only_seeded_demo_banners(self):
        from importlib import import_module
        from django.apps import apps as django_apps
        from apps.promotions.models import Banner
        demo = 'https://images.unsplash.com/photo-1596731498067-93a4b7174c93?w=1600'
        Banner.objects.create(title='Welcome Bonus', image_url=demo)
        Banner.objects.create(title='Welcome Bonus', image_url='https://cdn.example/our-own.jpg')
        module = import_module('apps.promotions.migrations.0006_remove_demo_banners')
        module.remove_demo_banners(django_apps, None)
        self.assertEqual(list(Banner.objects.values_list('image_url', flat=True)), ['https://cdn.example/our-own.jpg'])


class BannerImageUploadTests(TestCase):
    PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 64

    def setUp(self):
        from django.contrib.auth.models import User
        self.staff = User.objects.create(username='banner_staff', is_staff=True)
        self.player = User.objects.create(username='banner_player')

    def _upload(self, user, content, name='design.png'):
        from django.core.files.uploadedfile import SimpleUploadedFile
        api = APIClient()
        if user:
            api.force_authenticate(user)
        return api.post('/api/promotions/banner-images/', {'file': SimpleUploadedFile(name, content)}, format='multipart')

    def test_staff_upload_is_served_back(self):
        res = self._upload(self.staff, self.PNG)
        self.assertEqual(res.status_code, 201, res.content)
        url = res.json()['url']
        self.assertTrue(url.startswith('/api/promotions/banner-images/'))
        got = APIClient().get(url)
        self.assertEqual(got.status_code, 200)
        self.assertEqual(got['Content-Type'], 'image/png')
        self.assertIn('immutable', got['Cache-Control'])
        self.assertEqual(got.content, self.PNG)

    def test_only_staff_can_upload(self):
        self.assertIn(self._upload(None, self.PNG).status_code, (401, 403))
        self.assertEqual(self._upload(self.player, self.PNG).status_code, 403)

    def test_rejects_non_images_whatever_the_name(self):
        res = self._upload(self.staff, b'<html><script>alert(1)</script></html>', name='evil.png')
        self.assertEqual(res.status_code, 400)

    def test_missing_image_is_404(self):
        self.assertEqual(APIClient().get('/api/promotions/banner-images/999999/').status_code, 404)
