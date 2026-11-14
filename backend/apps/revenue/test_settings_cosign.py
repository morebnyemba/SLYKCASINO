"""Revenue-share settings save directly now (shares are edited per wallet, and a
cut needs the holder's consent — see test_shares). The co-signing machinery is
kept for any setting that should need every partner; it's tested here on a
temporarily governed path."""
import re
from datetime import timedelta

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

    def label(self, slot=1):
        return ShareWallet.objects.get(slot=slot).label


class DirectSaveTests(Base):
    def test_revenue_settings_are_no_longer_held(self):
        self.assertIsNone(changes.governed(RULES))
        res = jwt(self.boss).put(RULES, {'wallets': [{'slot': 1, 'label': 'Founder'}]}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(self.label(), 'Founder')

    def test_a_held_wallet_cant_be_reassigned_through_settings(self):
        res = jwt(self.boss).put(RULES, {'wallets': [{'slot': 2, 'holder_id': self.ops.id}]}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('consent', res.json()['detail'])
        self.assertEqual(ShareWallet.objects.get(slot=2).holder_id, self.p2.id)

    def test_django_admin_cant_edit_share_records(self):
        c = Client()
        c.force_login(self.boss)
        res = c.post(f'/django-admin/revenue/sharewallet/{ShareWallet.objects.get(slot=2).pk}/change/', {'holder': self.boss.id})
        self.assertEqual(res.status_code, 403)
        self.assertEqual(ShareWallet.objects.get(slot=2).holder_id, self.p2.id)

    def test_other_admin_actions_are_not_held(self):
        self.assertIsNone(changes.governed('/api/admin/withdrawals/5/mark-paid/'))
        self.assertIsNone(changes.governed('/api/admin/affiliate-programme/'))


class MachineryTests(Base):
    """The co-signing flow itself, on a path governed just for these tests."""

    def setUp(self):
        super().setUp()
        self._saved = changes._COMPILED
        changes._COMPILED = [(re.compile(r'^/api/admin/revenue-share/settings/$'), 'Revenue share settings')]

    def tearDown(self):
        changes._COMPILED = self._saved
        super().tearDown()

    def rename(self, user, name):
        return jwt(user).put(RULES, {'wallets': [{'slot': 1, 'label': name}]}, format='json')

    def test_a_save_waits_until_every_partner_approves(self):
        res = self.rename(self.boss, 'Founder')
        self.assertEqual(res.status_code, 202, res.content)
        self.assertEqual(res.json()['waiting_for'], ['partner2', 'partner3'])
        cid = res.json()['change_id']
        jwt(self.p2).post(f'/api/admin/settings-changes/{cid}/', {'decision': 'approve'}, format='json')
        self.assertNotEqual(self.label(), 'Founder')
        res = jwt(self.p3).post(f'/api/admin/settings-changes/{cid}/', {'decision': 'approve'}, format='json')
        self.assertEqual(res.json()['status'], 'applied', res.content)
        self.assertEqual(self.label(), 'Founder')

    def test_one_rejection_drops_it(self):
        cid = self.rename(self.boss, 'X').json()['change_id']
        res = jwt(self.p3).post(f'/api/admin/settings-changes/{cid}/', {'decision': 'reject', 'note': 'No thanks'}, format='json')
        self.assertEqual(res.json()['status'], 'rejected')
        self.assertNotEqual(self.label(), 'X')

    def test_open_changes_expire_after_a_week(self):
        cid = self.rename(self.boss, 'Y').json()['change_id']
        SettingsChange.objects.filter(pk=cid).update(created_at=timezone.now() - timedelta(days=8))
        res = jwt(self.p2).post(f'/api/admin/settings-changes/{cid}/', {'decision': 'approve'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertEqual(SettingsChange.objects.get(pk=cid).status, 'expired')

    def test_requester_can_withdraw_and_others_cant_vote_for_them(self):
        cid = self.rename(self.boss, 'Z').json()['change_id']
        self.assertEqual(jwt(self.ops).post(f'/api/admin/settings-changes/{cid}/', {'decision': 'approve'},
                                            format='json').status_code, 400)          # not a partner
        res = jwt(self.boss).post(f'/api/admin/settings-changes/{cid}/', {'cancel': True}, format='json')
        self.assertEqual(res.json()['status'], 'cancelled')
