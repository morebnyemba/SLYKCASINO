"""Bulk actions on the admin player list."""
from __future__ import annotations

import secrets
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts import services
from apps.accounts.models import AuditLog, Player
from apps.notifications.models import Notification
from apps.risk import services as risk
from apps.wallet import services as wallet_services

URL = '/api/players/bulk/'


class BulkPlayerTests(TestCase):
    def setUp(self):
        self.players = [services.create_player(username=f'bulk_{i}') for i in range(4)]
        self.ids = [p.id for p in self.players]
        self.staff = APIClient()
        self.staff.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))
        self.boss = APIClient()
        self.boss.force_authenticate(User.objects.create_superuser('boss', 'b@example.com', 'x'))

    def post(self, client, **body):
        return client.post(URL, body, format='json')

    def suspended(self):
        return sorted(Player.objects.filter(is_suspended=True).values_list('id', flat=True))

    def test_needs_staff(self):
        self.assertEqual(APIClient().post(URL, {'action': 'suspend'}, format='json').status_code, 401)
        with_login = services.register_player(username='has_login', email='hl@example.com',
                                              password=secrets.token_urlsafe(16), currency='USD')
        player_api = APIClient()
        player_api.force_authenticate(with_login.user)
        self.assertEqual(self.post(player_api, action='suspend', ids=self.ids, reason='x y z').status_code, 403)
        self.assertEqual(self.suspended(), [])

    def test_suspend_and_unsuspend_chosen_players(self):
        res = self.post(self.staff, action='suspend', ids=self.ids[:3], reason='Multi-account ring')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual((res.json()['requested'], res.json()['done']), (3, 3))
        self.assertEqual(self.suspended(), sorted(self.ids[:3]))
        self.assertEqual(Player.objects.get(pk=self.ids[0]).suspended_reason, 'Multi-account ring')
        self.assertEqual(AuditLog.objects.filter(event_type='player_bulk_action').count(), 3)
        self.assertEqual(AuditLog.objects.filter(event_type='players_bulk_action').count(), 1)
        res = self.post(self.staff, action='unsuspend', ids=self.ids)
        self.assertEqual((res.json()['done'], res.json()['skipped_count']), (3, 1))   # one was never suspended
        self.assertEqual(self.suspended(), [])

    def test_suspending_needs_a_reason(self):
        self.assertEqual(self.post(self.staff, action='suspend', ids=self.ids, reason=' ').status_code, 400)
        self.assertEqual(self.suspended(), [])

    def test_players_already_in_the_state_are_skipped_not_failed(self):
        services.suspend_player(self.ids[0], reason='earlier')
        res = self.post(self.staff, action='suspend', ids=self.ids[:2], reason='again please').json()
        self.assertEqual((res['done'], res['skipped_count'], res['failed_count']), (1, 1, 0))
        self.assertEqual(res['skipped'][0]['reason'], 'Already suspended')

    def test_staff_accounts_are_spared(self):
        staff_player = services.register_player(username='staffer', email='st@example.com',
                                                password=secrets.token_urlsafe(16), currency='USD')
        User.objects.filter(pk=staff_player.user_id).update(is_staff=True)
        res = self.post(self.staff, action='suspend', ids=[staff_player.id, self.ids[0]], reason='clean sweep').json()
        self.assertEqual((res['done'], res['skipped'][0]['reason']), (1, 'Staff account'))
        self.assertFalse(Player.objects.get(pk=staff_player.id).is_suspended)

    def test_freeze_withdrawals_and_block_bonuses_and_only_a_superuser_lifts_them(self):
        self.post(self.staff, action='freeze_withdrawals', ids=self.ids[:2])
        self.post(self.staff, action='block_bonus', ids=self.ids[:2])
        for pid in self.ids[:2]:
            prof = risk.profile(pid)
            self.assertTrue(prof.withdrawals_frozen and prof.bonus_blocked)
        self.assertFalse(risk.profile(self.ids[2]).withdrawals_frozen)
        self.assertEqual(self.post(self.staff, action='unfreeze_withdrawals', ids=self.ids[:2]).status_code, 400)
        self.assertTrue(risk.profile(self.ids[0]).withdrawals_frozen)
        res = self.post(self.boss, action='unfreeze_withdrawals', ids=self.ids).json()
        self.assertEqual((res['done'], res['skipped_count']), (2, 2))
        self.assertEqual(self.post(self.boss, action='unblock_bonus', ids=self.ids[:2]).json()['done'], 2)
        self.assertFalse(risk.profile(self.ids[0]).bonus_blocked)

    def test_notify_sends_each_player_the_message(self):
        res = self.post(self.staff, action='notify', ids=self.ids, title='Maintenance tonight', body='Back by 9pm.')
        self.assertEqual(res.json()['done'], 4)
        self.assertEqual(Notification.objects.filter(title='Maintenance tonight', body='Back by 9pm.').count(), 4)
        self.assertEqual(self.post(self.staff, action='notify', ids=self.ids, title='').status_code, 400)

    def test_select_all_matching_uses_the_list_filters(self):
        wallet_services.credit(player_id=self.ids[0], amount=Decimal('5'), kind='deposit', idempotency_key='b0')
        Player.objects.filter(pk=self.ids[3]).update(kyc_status='verified')
        res = self.post(self.staff, action='suspend', all_matching=True, filters={'kyc': 'verified'}, reason='kyc cleanup').json()
        self.assertEqual((res['requested'], res['done']), (1, 1))
        self.assertEqual(self.suspended(), [self.ids[3]])
        res = self.post(self.staff, action='unsuspend', all_matching=True, filters={'q': 'bulk_', 'status': 'suspended'}).json()
        self.assertEqual(res['done'], 1)
        self.assertEqual(self.suspended(), [])

    def test_bad_requests(self):
        self.assertEqual(self.post(self.staff, action='suspend', ids=[], reason='abc').status_code, 400)
        self.assertEqual(self.post(self.staff, action='suspend', ids='1,2', reason='abc').status_code, 400)
        self.assertEqual(self.post(self.staff, action='suspend', ids=[True], reason='abc').status_code, 400)
        self.assertEqual(self.post(self.staff, action='delete', ids=self.ids).status_code, 400)   # no bulk delete
        self.assertEqual(self.post(self.staff, ids=self.ids).status_code, 400)

    def test_too_many_players_is_refused_before_anything_changes(self):
        from apps.accounts import bulk
        original = bulk.MAX_PLAYERS
        bulk.MAX_PLAYERS = 2
        try:
            res = self.post(self.staff, action='suspend', all_matching=True, filters={}, reason='too many')
        finally:
            bulk.MAX_PLAYERS = original
        self.assertEqual(res.status_code, 400)
        self.assertEqual(self.suspended(), [])

    def test_the_list_still_sorts_by_balance_and_filters(self):
        wallet_services.credit(player_id=self.ids[2], amount=Decimal('50'), kind='deposit', idempotency_key='b2')
        rows = self.staff.get('/api/players/?page_size=10').json()['results']
        self.assertEqual(rows[0]['id'], self.ids[2])
        self.assertEqual(len(self.staff.get('/api/players/?q=bulk_1').json()['results']), 1)
