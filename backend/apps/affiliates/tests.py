"""Affiliate programme: joining, tracking, attribution, commission maths,
payouts (idempotent), recovery and the API."""
from __future__ import annotations

import secrets
from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as account_services
from apps.affiliates import services, utils
from apps.affiliates.models import Affiliate, AffiliateClick, Commission, Referral
from apps.affiliates.recovery import RecoveryManager
from apps.wallet import services as wallet_services

D = Decimal
PASSWORD = secrets.token_urlsafe(16)  # generated per run; test-only


class UtilsTests(SimpleTestCase):
    def test_ngr(self):
        # Staked 100 (sports 60 + casino 40), won back 70, got a 5 bonus -> 25.
        totals = {'bet_stake': D('-60'), 'bet_payout': D('50'), 'casino_debit': D('-40'),
                  'casino_credit': D('20'), 'bonus': D('5'), 'deposit': D('500')}
        self.assertEqual(utils.net_gaming_revenue(totals), D('25'))

    def test_commission_rounds_down_and_ignores_losing_months(self):
        self.assertEqual(utils.commission_for(D('33.33'), D('25')), D('8.33'))
        self.assertEqual(utils.commission_for(D('-50'), D('25')), D('0.00'))

    def test_months(self):
        self.assertEqual(utils.previous_month(date(2026, 1, 15)), date(2025, 12, 1))
        self.assertEqual(utils.next_month(date(2026, 12, 1)), date(2027, 1, 1))

    def test_mask(self):
        self.assertEqual(utils.mask_username('tendai_m'), 'te*****')
        self.assertEqual(utils.mask_username('ab'), 'a*')


class Base(TestCase):
    def setUp(self):
        self.partner = account_services.create_player(username='partner1')
        # These tests cover the core revenue-share / flat-CPA maths; the welcome
        # bonus, deposit-% commission, turnover rule and carry-over are switched
        # off here and covered in test_programme.py.
        services.update_programme(
            welcome_bonus_percent=0, default_cpa_percent=0, cpa_min_turnover_multiple=0, negative_carryover=False,
        )

    def make_affiliate(self, **terms):
        affiliate = services.apply(player_id=self.partner.id, code='PARTNER')
        services.set_status(affiliate.id, Affiliate.Status.ACTIVE)
        if terms:
            services.update_terms(affiliate.id, **terms)
        affiliate.refresh_from_db()
        return affiliate

    def referred(self, name, affiliate):
        player = account_services.create_player(username=name)
        services.attach_referral(player_id=player.id, code=affiliate.code)
        return player

    def play(self, player, *, staked, won, bonus=0, deposit=0):
        key = f'{player.id}:{staked}:{won}:{bonus}:{deposit}'
        if deposit:
            wallet_services.credit(player_id=player.id, amount=D(deposit), kind='deposit', idempotency_key=f'd{key}')
        else:
            wallet_services.credit(player_id=player.id, amount=D(staked), kind='deposit', idempotency_key=f'd{key}')
        wallet_services.debit(player_id=player.id, amount=D(staked), kind='bet_stake', idempotency_key=f's{key}')
        if won:
            wallet_services.credit(player_id=player.id, amount=D(won), kind='bet_payout', idempotency_key=f'w{key}')
        if bonus:
            wallet_services.credit(player_id=player.id, amount=D(bonus), kind='bonus', idempotency_key=f'b{key}')


class MembershipTests(Base):
    def test_apply_is_pending_and_idempotent(self):
        a = services.apply(player_id=self.partner.id)
        self.assertEqual(a.status, Affiliate.Status.PENDING)
        self.assertTrue(a.code.startswith('PARTNE'))
        self.assertEqual(services.apply(player_id=self.partner.id).pk, a.pk)
        self.assertEqual(a.revshare_percent, D('25'))

    @override_settings(AFFILIATE_AUTO_APPROVE=True)
    def test_auto_approve(self):
        self.assertEqual(services.apply(player_id=self.partner.id).status, Affiliate.Status.ACTIVE)

    def test_custom_code_rules(self):
        with self.assertRaises(services.AffiliateError):
            services.apply(player_id=self.partner.id, code='x')
        services.apply(player_id=self.partner.id, code='my-code 1')
        self.assertTrue(Affiliate.objects.filter(code='MYCODE1').exists())
        other = account_services.create_player(username='other')
        with self.assertRaises(services.AffiliateError):
            services.apply(player_id=other.id, code='MYCODE1')

    def test_terms_validation(self):
        a = self.make_affiliate()
        with self.assertRaises(services.AffiliateError):
            services.update_terms(a.id, revshare_percent=150)
        services.update_terms(a.id, revshare_percent='40', cpa_amount='10')
        a.refresh_from_db()
        self.assertEqual((a.revshare_percent, a.cpa_amount), (D('40'), D('10')))


class AttributionTests(Base):
    def test_referrals_only_for_active_affiliates_and_never_self(self):
        pending = services.apply(player_id=self.partner.id, code='PARTNER')
        p1 = account_services.create_player(username='early')
        self.assertIsNone(services.attach_referral(player_id=p1.id, code='PARTNER'))
        services.set_status(pending.id, Affiliate.Status.ACTIVE)
        self.assertIsNone(services.attach_referral(player_id=self.partner.id, code='partner'))
        p2 = account_services.create_player(username='friend')
        self.assertIsNotNone(services.attach_referral(player_id=p2.id, code='partner'))
        # A player belongs to one affiliate, fixed at signup.
        self.assertIsNone(services.attach_referral(player_id=p2.id, code='PARTNER'))
        self.assertEqual(Referral.objects.count(), 1)

    def test_clicks(self):
        a = self.make_affiliate()
        self.assertTrue(services.record_click('partner', campaign='tiktok', landing='/sportsbook'))
        self.assertFalse(services.record_click('NOPE'))
        self.assertEqual(AffiliateClick.objects.get().campaign, 'tiktok')
        self.assertEqual(a.clicks.count(), 1)


class CommissionTests(Base):
    def setUp(self):
        super().setUp()
        self.affiliate = self.make_affiliate(cpa_amount='15', cpa_min_deposit='50')
        self.month = utils.month_start(timezone.localdate())

    def test_revshare_on_net_revenue_is_idempotent(self):
        a = self.referred('alice', self.affiliate)
        b = self.referred('bob', self.affiliate)
        self.play(a, staked=100, won=20)            # +80
        self.play(b, staked=50, won=70, bonus=10)   # -30
        outsider = account_services.create_player(username='outsider')
        self.play(outsider, staked=1000, won=0)     # not referred: ignored
        c = services.compute_revshare(self.affiliate, self.month)
        self.assertEqual((c.base_amount, c.amount, c.active_players), (D('50'), D('12.50'), 2))
        self.assertEqual(services.compute_revshare(self.affiliate, self.month).pk, c.pk)
        self.assertEqual(Commission.objects.count(), 1)

    def test_losing_month_pays_nothing(self):
        a = self.referred('alice', self.affiliate)
        self.play(a, staked=10, won=100)
        self.assertIsNone(services.compute_revshare(self.affiliate, self.month))

    def test_cpa_after_threshold_once(self):
        a = self.referred('alice', self.affiliate)
        wallet_services.credit(player_id=a.id, amount=D('30'), kind='deposit', idempotency_key='cpa1')
        self.assertEqual(services.compute_cpa(self.affiliate), 0)
        wallet_services.credit(player_id=a.id, amount=D('30'), kind='deposit', idempotency_key='cpa2')
        self.assertEqual(services.compute_cpa(self.affiliate), 1)
        self.assertEqual(services.compute_cpa(self.affiliate), 0)
        self.assertEqual(Commission.objects.get(kind='cpa').amount, D('15'))

    def test_run_closes_previous_month(self):
        a = self.referred('alice', self.affiliate)
        self.play(a, staked=100, won=0)
        result = services.run_commissions(today=utils.next_month(self.month) + timedelta(days=2))
        self.assertEqual((result['revshare'], result['period']), (1, self.month.isoformat()))
        self.assertEqual(services.run_commissions(today=utils.next_month(self.month))['revshare'], 1)
        self.assertEqual(Commission.objects.filter(kind='revshare').count(), 1)

    def test_approve_adds_to_balance_once_and_reject(self):
        a = self.referred('alice', self.affiliate)
        self.play(a, staked=100, won=0)
        c = services.compute_revshare(self.affiliate, self.month)
        self.assertEqual(services.balance(self.affiliate)['pending'], D('25.00'))
        services.approve(c.id)
        services.approve(c.id)
        self.assertEqual(services.balance(self.affiliate)['available'], D('25.00'))
        self.assertEqual(wallet_services.get_balance(self.partner.id), D('0'))  # not paid until requested
        c.refresh_from_db()
        self.assertEqual(c.status, Commission.Status.APPROVED)
        with self.assertRaises(services.AffiliateError):
            services.reject(c.id)

    @override_settings(AFFILIATE_AUTO_PAY=True)
    def test_auto_pay(self):
        a = self.referred('alice', self.affiliate)
        self.play(a, staked=100, won=0)
        self.assertEqual(services.compute_revshare(self.affiliate, self.month).status, Commission.Status.APPROVED)
        self.assertEqual(services.balance(self.affiliate)['available'], D('25.00'))

    def test_recovery_completes_stuck_wallet_payout(self):
        from apps.affiliates.models import Payout
        a = self.referred('alice', self.affiliate)
        self.play(a, staked=100, won=0)
        services.approve(services.compute_revshare(self.affiliate, self.month).id)
        # A wallet payout whose credit never happened (crash between the two writes).
        stuck = Payout.objects.create(affiliate=self.affiliate, amount=D('25.00'), method=Payout.Method.WALLET)
        Payout.objects.filter(pk=stuck.pk).update(created_at=timezone.now() - timedelta(hours=1))
        report = RecoveryManager().run()
        self.assertTrue(report.ok)
        stuck.refresh_from_db()
        self.assertEqual(stuck.status, Payout.Status.PAID)
        self.assertEqual(wallet_services.get_balance(self.partner.id), D('25.00'))
        self.assertTrue(RecoveryManager().run().ok)
        self.assertEqual(wallet_services.get_balance(self.partner.id), D('25.00'))

    def test_dashboard(self):
        a = self.referred('alice', self.affiliate)
        self.play(a, staked=100, won=40)
        services.record_click('PARTNER')
        stats = services.dashboard(self.affiliate)
        self.assertEqual((stats['signups'], stats['depositors'], stats['clicks_30d']), (1, 1, 1))
        self.assertEqual((stats['ngr_this_month'], stats['estimated_commission']), (D('60'), D('15.00')))
        self.assertEqual(stats['referrals'][0]['player'], 'al***')


class ApiTests(Base):
    def client_for(self, player, staff=False):
        user = User.objects.create_user(username=player.username, password='pw', is_staff=staff)
        player.user = user
        player.save(update_fields=['user'])
        client = APIClient()
        client.force_authenticate(user)
        return client

    def test_player_flow(self):
        client = self.client_for(self.partner)
        self.assertEqual(client.get('/api/affiliates/me/').status_code, 404)
        res = client.post('/api/affiliates/me/', {'code': 'PARTNER'}, format='json')
        self.assertEqual((res.status_code, res.json()['status']), (201, 'pending'))
        self.assertNotIn('stats', client.get('/api/affiliates/me/').json())
        Affiliate.objects.update(status='active')
        data = client.get('/api/affiliates/me/').json()
        self.assertEqual(data['stats']['signups'], 0)

    def test_signup_through_link_and_click(self):
        cache.clear()  # signup is rate limited per IP; earlier tests may have used it up
        self.make_affiliate()
        self.assertTrue(APIClient().post('/api/affiliates/click/', {'code': 'PARTNER'}, format='json').json()['tracked'])
        res = APIClient().post('/api/auth/register/', {
            'username': 'newbie', 'email': 'newbie@example.com', 'password': PASSWORD, 'ref': 'partner',
            'accept_terms': True,
        }, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(Referral.objects.get().affiliate.code, 'PARTNER')

    def test_admin_endpoints_are_staff_only_and_work(self):
        a = services.apply(player_id=self.partner.id, code='PARTNER')
        player_client = self.client_for(self.partner)
        self.assertEqual(player_client.get('/api/admin/affiliates/').status_code, 403)
        staff = account_services.create_player(username='boss')
        admin = self.client_for(staff, staff=True)
        rows = admin.get('/api/admin/affiliates/').json()
        rows = rows.get('results', rows)
        self.assertEqual(rows[0]['username'], 'partner1')
        self.assertEqual(admin.post(f'/api/admin/affiliates/{a.id}/status/', {'status': 'active'}, format='json').json()['status'], 'active')
        res = admin.post(f'/api/admin/affiliates/{a.id}/terms/', {'revshare_percent': '35'}, format='json')
        self.assertEqual(res.json()['revshare_percent'], '35.00')
        self.assertEqual(admin.post('/api/admin/affiliate-commissions/run/', {}, format='json').status_code, 200)
