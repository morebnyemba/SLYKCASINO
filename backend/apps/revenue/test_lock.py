"""The founder's password lock on the revenue share."""
from __future__ import annotations

from io import StringIO

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.management import call_command
from django.test import Client, TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.revenue import lock, services
from apps.revenue.models import RevenueSettings

LOCK = '/api/admin/revenue-share/lock/'
PW = 'mindwell-secret-1'


class LockTests(TestCase):
    def setUp(self):
        cache.clear()
        self.mindwell = User.objects.create_superuser('mindwell', 'm@example.com', 'x')     # wallet 1: the founder
        self.admin = User.objects.create_superuser('admin', 'a@example.com', 'x')           # another superuser
        self.clerk = User.objects.create_user('clerk', 'c@example.com', 'x', is_staff=True)
        RevenueSettings.load()
        services.update_settings(wallets=[{'slot': 1, 'holder_id': self.mindwell.id}], by='setup')

    def api(self, user):
        c = APIClient()             # a real token: the lock runs before the API's own authentication
        c.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(user).access_token}')
        return c

    def lock_it(self):
        res = self.api(self.mindwell).post(LOCK, {'password': PW}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        return res.json()

    def test_only_the_founder_sets_it(self):
        res = self.api(self.admin).post(LOCK, {'password': PW}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('founder', res.json()['detail'])
        self.assertEqual(self.api(self.mindwell).post(LOCK, {'password': 'short'}, format='json').status_code, 400)
        body = self.lock_it()
        self.assertEqual((body['locked'], body['owner'], body['can_manage'], body['has_access']), (True, 'mindwell', True, True))
        self.assertNotIn(PW, RevenueSettings.load().lock_hash)

    def test_locked_means_423_for_everyone_else_everywhere(self):
        self.assertEqual(self.api(self.admin).get('/api/admin/revenue-share/').status_code, 200)
        self.lock_it()
        for path in ('/api/admin/revenue-share/', '/api/admin/revenue-share/shares/', '/api/admin/revenue-share/pool/',
                     '/api/admin/settings-changes/', '/api/admin/liabilities/partners/'):
            res = self.api(self.admin).get(path)
            self.assertEqual(res.status_code, 423, path)
            self.assertIn('locked by mindwell', res.json()['detail'])
        self.assertEqual(self.api(self.admin).post('/api/admin/revenue-share/shares/set/', {'slot': 1, 'percent': '1'},
                                                   format='json').status_code, 423)
        self.assertEqual(self.api(self.mindwell).get('/api/admin/revenue-share/').status_code, 200)   # the founder is in
        status = self.api(self.admin).get(LOCK).json()                                               # the lock page is open
        self.assertEqual((status['locked'], status['has_access'], status['can_manage']), (True, False, False))
        summary = self.api(self.admin).get('/api/admin/liabilities/').json()
        self.assertIsNone(summary.get('partners'))                                                   # partners hidden

    def test_the_password_opens_it_for_that_login_and_close_locks_it_again(self):
        self.lock_it()
        res = self.api(self.admin).post(LOCK + 'unlock/', {'password': 'wrong-one'}, format='json')
        self.assertEqual(res.status_code, 400)
        res = self.api(self.admin).post(LOCK + 'unlock/', {'password': PW}, format='json')
        self.assertTrue(res.json()['has_access'])
        self.assertEqual(self.api(self.admin).get('/api/admin/revenue-share/').status_code, 200)
        self.assertEqual(self.api(self.clerk).get('/api/admin/revenue-share/').status_code, 423)    # only that login
        self.api(self.admin).post(LOCK + 'unlock/', {'close': True}, format='json')
        self.assertEqual(self.api(self.admin).get('/api/admin/revenue-share/').status_code, 423)

    def test_changing_the_password_closes_every_opened_session(self):
        self.lock_it()
        self.api(self.admin).post(LOCK + 'unlock/', {'password': PW}, format='json')
        res = self.api(self.mindwell).post(LOCK, {'password': 'new-secret-22'}, format='json')
        self.assertEqual(res.status_code, 400)                                                       # needs the current one
        res = self.api(self.mindwell).post(LOCK, {'password': 'new-secret-22', 'current': PW}, format='json')
        self.assertEqual(res.status_code, 200)
        self.assertEqual(self.api(self.admin).get('/api/admin/revenue-share/').status_code, 423)
        self.assertEqual(self.api(self.admin).post(LOCK, {'password': 'x' * 12, 'current': 'new-secret-22'},
                                                   format='json').status_code, 400)                  # only the owner changes it

    def test_guessing_is_capped(self):
        self.lock_it()
        for _ in range(lock.TRIES):
            self.api(self.admin).post(LOCK + 'unlock/', {'password': 'nope-nope'}, format='json')
        res = self.api(self.admin).post(LOCK + 'unlock/', {'password': PW}, format='json')
        self.assertIn('Too many', res.json()['detail'])

    def test_the_founder_removes_it_and_the_server_can_clear_it(self):
        self.lock_it()
        self.assertEqual(self.api(self.mindwell).delete(LOCK, {'password': 'wrong-one'}, format='json').status_code, 400)
        self.assertFalse(self.api(self.mindwell).delete(LOCK, {'password': PW}, format='json').json()['locked'])
        self.assertEqual(self.api(self.admin).get('/api/admin/revenue-share/').status_code, 200)
        self.lock_it()
        out = StringIO()
        call_command('revenue_lock', stdout=out)
        self.assertIn('Locked by mindwell', out.getvalue())
        call_command('revenue_lock', '--clear', stdout=StringIO())
        self.assertFalse(lock.is_locked())

    def test_django_admin_revenue_section_is_locked_too(self):
        self.lock_it()
        c = Client()
        c.force_login(self.admin)
        self.assertEqual(c.get('/django-admin/revenue/').status_code, 423)
        c.force_login(self.mindwell)
        self.assertNotEqual(c.get('/django-admin/revenue/').status_code, 423)

    def test_the_audit_log_records_it(self):
        from apps.accounts.models import AuditLog
        self.lock_it()
        self.api(self.admin).post(LOCK + 'unlock/', {'password': 'wrong-one'}, format='json')
        self.api(self.admin).post(LOCK + 'unlock/', {'password': PW}, format='json')
        kinds = set(AuditLog.objects.values_list('event_type', flat=True))
        self.assertTrue({'revenue_locked', 'revenue_unlock_failed', 'revenue_opened'} <= kinds)
