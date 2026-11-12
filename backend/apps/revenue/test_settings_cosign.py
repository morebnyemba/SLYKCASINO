"""Revenue-share settings change only when every partner co-signs."""
from datetime import timedelta
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import Client, TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.revenue import changes
from apps.revenue.models import RevenueSettings, SettingsChange, ShareWallet

PW = 'Str0ng-pass-123'
RULES = '/api/admin/revenue-share/settings/'


def jwt(user):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
    return c


class Base(TestCase):
    def setUp(self):
        self.boss = User.objects.create_superuser('boss', 'b@example.com', PW)
        self.p2 = User.objects.create_user('partner2', 'p2@example.com', PW, is_staff=True)
        self.p3 = User.objects.create_user('partner3', 'p3@example.com', PW, is_staff=True)
        self.ops = User.objects.create_superuser('ops', 'o@example.com', PW)
        ShareWallet.ensure()
        for slot, user in ((1, self.boss), (2, self.p2), (3, self.p3)):
            ShareWallet.objects.filter(slot=slot).update(holder=user)
        RevenueSettings.load()

    def share(self):
        return RevenueSettings.load().share_percent


class CosignTests(Base):
    def test_a_save_waits_until_every_partner_approves(self):
        before = self.share()
        res = jwt(self.boss).put(RULES, {'share_percent': '20.00'}, format='json')
        self.assertEqual(res.status_code, 202, res.content)
        self.assertEqual(res.json()['waiting_for'], ['partner2', 'partner3'])
        self.assertEqual(self.share(), before)                     # not applied
        cid = res.json()['change_id']
        row = jwt(self.p2).get('/api/admin/settings-changes/').json()
        self.assertEqual(row['pending_for_me'], 1)
        self.assertEqual(row['changes'][0]['diff'], [{'field': 'share_percent', 'before': f'{before:.2f}', 'after': '20.00'}])
        jwt(self.p2).post(f'/api/admin/settings-changes/{cid}/', {'decision': 'approve'}, format='json')
        self.assertEqual(self.share(), before)
        res = jwt(self.p3).post(f'/api/admin/settings-changes/{cid}/', {'decision': 'approve'}, format='json')
        self.assertEqual(res.json()['status'], 'applied', res.content)
        self.assertEqual(self.share(), D('20.00'))

    def test_one_rejection_drops_it(self):
        cid = jwt(self.boss).put(RULES, {'share_percent': '30.00'}, format='json').json()['change_id']
        res = jwt(self.p3).post(f'/api/admin/settings-changes/{cid}/', {'decision': 'reject', 'note': 'Too high'}, format='json')
        self.assertEqual(res.json()['status'], 'rejected')
        self.assertNotEqual(self.share(), D('30.00'))

    def test_a_staff_login_that_isnt_a_partner_needs_all_three(self):
        res = jwt(self.ops).put(RULES, {'share_percent': '15.00'}, format='json')
        self.assertEqual(res.json()['waiting_for'], ['boss', 'partner2', 'partner3'])

    def test_wallet_holders_cant_be_reassigned_alone(self):
        res = jwt(self.boss).put(RULES, {'wallets': [{'slot': 2, 'holder_id': self.ops.id}]}, format='json')
        self.assertEqual(res.status_code, 202)
        self.assertEqual(ShareWallet.objects.get(slot=2).holder_id, self.p2.id)
        diff = jwt(self.p2).get('/api/admin/settings-changes/').json()['changes'][0]['diff']
        self.assertEqual(diff, [{'field': 'Wallet 2 holder', 'before': 'partner2', 'after': 'ops'}])

    def test_other_settings_are_not_held(self):
        from apps.wallet.models import WalletRules
        res = jwt(self.boss).put('/api/admin/wallet-rules/', {'min_stake': '2.00'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(WalletRules.load().min_stake, D('2.00'))

    def test_a_second_change_is_superseded_when_the_first_applies(self):
        first = jwt(self.boss).put(RULES, {'share_percent': '20.00'}, format='json').json()['change_id']
        second = jwt(self.p2).put(RULES, {'share_percent': '25.00'}, format='json').json()['change_id']
        for u in (self.p2, self.p3):
            jwt(u).post(f'/api/admin/settings-changes/{first}/', {'decision': 'approve'}, format='json')
        self.assertEqual(SettingsChange.objects.get(pk=second).status, 'superseded')

    def test_invalid_values_fail_on_apply_with_the_reason(self):
        cid = jwt(self.boss).put(RULES, {'share_percent': '50'}, format='json').json()['change_id']    # over 33.33%
        jwt(self.p2).post(f'/api/admin/settings-changes/{cid}/', {'decision': 'approve'}, format='json')
        res = jwt(self.p3).post(f'/api/admin/settings-changes/{cid}/', {'decision': 'approve'}, format='json').json()
        self.assertEqual(res['status'], 'failed')
        self.assertTrue(res['result_detail'])

    def test_open_changes_expire_after_a_week(self):
        cid = jwt(self.boss).put(RULES, {'share_percent': '20.00'}, format='json').json()['change_id']
        SettingsChange.objects.filter(pk=cid).update(created_at=timezone.now() - timedelta(days=8))
        res = jwt(self.p2).post(f'/api/admin/settings-changes/{cid}/', {'decision': 'approve'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(SettingsChange.objects.get(pk=cid).status, 'expired')

    def test_requester_can_withdraw_and_others_cant_vote_for_them(self):
        cid = jwt(self.boss).put(RULES, {'share_percent': '20.00'}, format='json').json()['change_id']
        self.assertEqual(jwt(self.ops).post(f'/api/admin/settings-changes/{cid}/', {'decision': 'approve'},
                                            format='json').status_code, 400)          # not a partner
        res = jwt(self.boss).post(f'/api/admin/settings-changes/{cid}/', {'cancel': True}, format='json')
        self.assertEqual(res.json()['status'], 'cancelled')

    def test_django_admin_cant_edit_governed_records(self):
        c = Client()
        c.force_login(self.boss)
        res = c.post(f'/django-admin/revenue/sharewallet/{ShareWallet.objects.get(slot=2).pk}/change/', {'holder': self.boss.id})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(ShareWallet.objects.get(slot=2).holder_id, self.p2.id)

    def test_with_no_other_partner_a_save_applies_at_once(self):
        ShareWallet.objects.filter(slot__in=(2, 3)).update(holder=None)
        res = jwt(self.boss).put(RULES, {'share_percent': '20.00'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.share(), D('20.00'))

    def test_other_admin_actions_are_not_held(self):
        self.assertIsNone(changes.governed('/api/admin/withdrawals/5/mark-paid/'))
        self.assertIsNone(changes.governed('/api/admin/affiliate-programme/'))
        self.assertIsNotNone(changes.governed('/api/admin/revenue-share/settings/'))
