"""Staff "view as player" sessions (apps.accounts.impersonation)."""
import secrets
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts import services
from apps.accounts.models import AuditLog

# Throwaway per run; never a fixed string in the repo.
PASSWORD = secrets.token_urlsafe(16)


class ImpersonationTests(TestCase):
    def setUp(self):
        self.player = services.register_player(username='punter', email='p@example.com', password=PASSWORD)
        self.staff = User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True)
        self.boss = User.objects.create_user('boss', 'b@example.com', 'x', is_staff=True, is_superuser=True)

    def start(self, user, mode='view', reason='Checking a ticket complaint', player=None):
        api = APIClient()
        api.force_authenticate(user)
        return api.post(f'/api/players/{(player or self.player).id}/impersonate/', {'mode': mode, 'reason': reason}, format='json')

    def session(self, user, mode='view'):
        """Exchange the minted token as the player site does; returns an API client signed in with it."""
        minted = self.start(user, mode).json()['refresh']
        tokens = APIClient().post('/api/auth/refresh/', {'refresh': minted}, format='json').json()
        api = APIClient()
        api.credentials(HTTP_AUTHORIZATION=f'Bearer {tokens["access"]}')
        return api, tokens, minted

    def test_view_session_reads_as_the_player_and_cannot_write(self):
        api, tokens, minted = self.session(self.staff)
        self.assertEqual(api.get('/api/players/me/').json()['username'], 'punter')
        res = api.post('/api/support/messages/', {'body': 'hi'}, format='json')
        self.assertEqual(res.status_code, 403)
        self.assertIn('View-only', res.json()['detail'])
        # The minted token is single-use: the exchange blacklisted it.
        self.assertEqual(APIClient().post('/api/auth/refresh/', {'refresh': minted}, format='json').status_code, 401)
        # Ending the session is the one write allowed.
        self.assertEqual(api.post('/api/auth/logout/', {'refresh': tokens['refresh']}, format='json').status_code, 204)
        log = AuditLog.objects.get(event_type='impersonation_started')
        self.assertEqual((log.player_id, log.metadata['by'], log.metadata['mode']), (self.player.id, 'ops', 'view'))

    def test_full_session_is_superuser_only_and_audits_writes(self):
        self.assertEqual(self.start(self.staff, mode='full').status_code, 403)
        api, _, _ = self.session(self.boss, mode='full')
        self.assertEqual(api.post('/api/support/messages/', {'body': 'hi'}, format='json').status_code, 201)
        log = AuditLog.objects.get(event_type='impersonated_action')
        self.assertEqual((log.metadata['by'], log.metadata['path']), ('boss', '/api/support/messages/'))

    def test_refusals(self):
        self.assertEqual(self.start(self.staff, reason='').status_code, 400)
        staff_player = services.register_player(username='teammate', email='t@example.com', password=PASSWORD)
        staff_player.user.is_staff = True
        staff_player.user.save()
        self.assertEqual(self.start(self.boss, player=staff_player).status_code, 403)
        self.assertIn(APIClient().post(f'/api/players/{self.player.id}/impersonate/', {}).status_code, (401, 403))
        player_api = APIClient()
        player_api.force_authenticate(self.player.user)
        self.assertEqual(player_api.post(f'/api/players/{self.player.id}/impersonate/', {'reason': 'xyz'}).status_code, 403)

    def test_session_ends_on_time_even_after_refreshing(self):
        api, tokens, _ = self.session(self.staff)
        later = __import__('time').time() + 2 * 3600
        with mock.patch('apps.accounts.impersonation.time.time', return_value=later):
            self.assertEqual(api.get('/api/players/me/').status_code, 401)
            self.assertEqual(APIClient().post('/api/auth/refresh/', {'refresh': tokens['refresh']}, format='json').status_code, 401)

    def test_viewing_support_chat_keeps_replies_unread(self):
        from apps.livechat import support
        support.staff_reply(player_id=self.player.id, body='We fixed it', staff_name='ops')
        api, _, _ = self.session(self.staff)
        self.assertEqual(api.get('/api/support/messages/').status_code, 200)
        self.assertEqual(support.unread_for_player(self.player.id), 1)
