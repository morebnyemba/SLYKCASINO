"""Deposit promotions: a % of the deposit by amount, credited on the deposit."""
from datetime import timedelta
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from apps.affiliates import services as affiliates
from apps.affiliates.models import Affiliate
from apps.promotions import services
from apps.promotions.models import DepositBonus, PromotionClaim
from apps.wallet import services as wallet


class DepositBonusTests(TestCase):
    def setUp(self):
        self.player = accounts.create_player(username='punter')
        self.small = DepositBonus.objects.create(name='Starter', min_deposit=D('10'), max_deposit=D('49.99'), percent=D('10'))
        self.big = DepositBonus.objects.create(name='Big', min_deposit=D('50'), percent=D('25'), max_bonus=D('40'),
                                               wagering_multiplier=D('3'))
        self.n = 0

    def deposit(self, amount, player=None):
        self.n += 1
        wallet.deposit(player_id=(player or self.player).id, amount=D(amount), idempotency_key=f'dep{self.n}')

    def bonus_total(self, player=None):
        return wallet.totals_by_kind([(player or self.player).id]).get((player or self.player).id, {}).get('bonus', D('0'))

    def test_percentage_depends_on_the_amount(self):
        self.deposit('5')                      # below every tier
        self.assertEqual(self.bonus_total(), D('0'))
        self.deposit('20')                     # 10% → 2
        self.deposit('100')                    # 25% → 25
        self.deposit('400')                    # 25% → 100, capped at 40
        self.assertEqual(self.bonus_total(), D('67.00'))
        claim = PromotionClaim.objects.filter(promotion__code=f'deposit-bonus:{self.big.id}').order_by('created_at').first()
        self.assertEqual((claim.bonus_amount, claim.wagering_required), (D('25.00'), D('75.00')))
        self.assertEqual(services.bonus_status(self.player.id)['locked'], D('67.00'))  # not withdrawable yet

    def test_limits_dates_and_switching_off(self):
        self.big.limit = DepositBonus.Limit.ONCE
        self.big.save()
        self.deposit('100')
        self.deposit('100')                    # already used
        self.assertEqual(self.bonus_total(), D('25.00'))
        self.small.limit = DepositBonus.Limit.DAILY
        self.small.save()
        self.deposit('20')
        self.deposit('20')                     # once a day
        self.assertEqual(self.bonus_total(), D('27.00'))
        self.small.active = False
        self.small.save()
        other = accounts.create_player(username='other')
        self.deposit('20', other)
        self.assertEqual(self.bonus_total(other), D('0'))
        self.big.ends_at = timezone.now() - timedelta(minutes=1)
        self.big.limit = DepositBonus.Limit.EVERY
        self.big.save()
        self.deposit('100', other)
        self.assertEqual(self.bonus_total(other), D('0'))

    def test_not_stacked_with_the_referral_welcome_bonus(self):
        agent = accounts.create_player(username='agent')
        a = affiliates.apply(player_id=agent.id, code='AGENT')
        affiliates.set_status(a.id, Affiliate.Status.ACTIVE)
        affiliates.update_programme(welcome_bonus_percent=30, welcome_bonus_cap=100)
        friend = accounts.create_player(username='friend')
        affiliates.attach_referral(player_id=friend.id, code='AGENT')
        self.deposit('100', friend)            # first deposit: welcome bonus 30, not the 25 promo
        self.assertEqual(self.bonus_total(friend), D('30.00'))
        self.deposit('100', friend)            # later deposits: the promotion
        self.assertEqual(self.bonus_total(friend), D('55.00'))

    def test_admin_api_and_public_list(self):
        staff = APIClient()
        staff.force_authenticate(User.objects.create_user('ops', 'ops@example.com', 'x', is_staff=True))
        r = staff.post('/api/admin/deposit-bonuses/', {'name': 'Weekend', 'min_deposit': '20', 'max_deposit': '10', 'percent': '50'}, format='json')
        self.assertEqual(r.status_code, 400)
        r = staff.post('/api/admin/deposit-bonuses/', {'name': 'Weekend', 'min_deposit': '200', 'percent': '50',
                                                       'limit': 'daily'}, format='json')
        self.assertEqual(r.status_code, 201)
        self.deposit('100')
        rows = {row['name']: row for row in staff.get('/api/admin/deposit-bonuses/').json()}
        self.assertEqual((rows['Big']['given'], rows['Big']['total_given']), (1, '25.00'))
        staff.patch(f"/api/admin/deposit-bonuses/{rows['Weekend']['id']}/", {'active': False}, format='json')
        listed = staff.get('/api/promotions/').json()
        listed = listed['results'] if isinstance(listed, dict) else listed
        self.assertFalse([p for p in listed if p['code'].startswith('deposit-bonus:')])  # managed as tiers only
        public = APIClient().get('/api/promotions/deposit-bonuses/').json()
        self.assertEqual([t['name'] for t in public], ['Starter', 'Big'])
        self.assertEqual(APIClient().get('/api/admin/deposit-bonuses/').status_code, 401)

    def test_players_see_which_limited_bonuses_they_used(self):
        import secrets
        self.player = accounts.register_player(username='member', email='m@example.com', password=secrets.token_urlsafe(16))
        self.big.limit = DepositBonus.Limit.ONCE
        self.big.save()
        self.deposit('100')
        api = APIClient()
        api.force_authenticate(self.player.user)
        used = {t['name']: t['used'] for t in api.get('/api/promotions/deposit-bonuses/').json()}
        self.assertEqual(used, {'Starter': False, 'Big': True})
        claims = api.get('/api/promotions/my-claims/').json()
        rows = claims['results'] if isinstance(claims, dict) else claims
        self.assertEqual(rows[0]['promotion_code'], f'deposit-bonus:{self.big.id}')
