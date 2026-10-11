"""Private support chat: a player sees only their own conversation; staff see
every conversation; the old public lobby is gone."""
from __future__ import annotations

from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as account_services
from apps.livechat.models import ChatMessage
from apps.notifications.models import Notification


def _client_for(name):
    player = account_services.create_player(username=name)
    user = User.objects.create(username=name)
    player.user = user
    player.save(update_fields=['user'])
    api = APIClient()
    api.force_authenticate(user)
    return player, api


class PrivateSupportTests(TestCase):
    def setUp(self):
        self.alice, self.alice_api = _client_for('alice')
        self.bob, self.bob_api = _client_for('bob')
        self.staff = APIClient()
        self.staff.force_authenticate(User.objects.create_user('agent', 'a@example.com', 'x', is_staff=True,
                                                               first_name='Rudo'))

    def say(self, api, body):
        res = api.post('/api/support/messages/', {'body': body}, format='json')
        ChatMessage.objects.update(created_at=timezone.now() - timedelta(seconds=5))  # past the rate limit
        return res

    def test_players_only_see_their_own_conversation(self):
        self.assertEqual(self.say(self.alice_api, 'My withdrawal is missing').status_code, 201)
        self.say(self.bob_api, 'How do I deposit?')
        alice = self.alice_api.get('/api/support/messages/').json()['results']
        self.assertEqual([m['body'] for m in alice], ['My withdrawal is missing'])
        self.assertEqual([m['body'] for m in self.bob_api.get('/api/support/messages/').json()['results']], ['How do I deposit?'])
        self.assertEqual(APIClient().get('/api/support/messages/').status_code, 401)
        self.assertEqual(self.alice_api.get('/api/chat/', {'channel': f'support:{self.bob.id}'}).status_code, 404)  # lobby gone
        self.assertEqual(self.alice_api.get(f'/api/admin/support/{self.bob.id}/').status_code, 403)

    def test_staff_inbox_reply_and_read_receipts(self):
        self.say(self.alice_api, 'Hello?')
        self.say(self.alice_api, 'Anyone there?')
        inbox = self.staff.get('/api/admin/support/').json()
        row = inbox['results'][0]
        self.assertEqual((row['username'], row['unread'], row['last_body']), ('alice', 2, 'Anyone there?'))
        self.assertEqual(inbox['unread_threads'], 1)
        self.assertEqual(self.staff.get('/api/admin/stats/').json()['queues']['support_unread'], 1)

        thread = self.staff.get(f'/api/admin/support/{self.alice.id}/').json()
        self.assertEqual([m['sender'] for m in thread['results']], ['alice', 'alice'])
        self.assertEqual(self.staff.get('/api/admin/support/').json()['results'][0]['unread'], 0)  # opened = read

        res = self.staff.post(f'/api/admin/support/{self.alice.id}/', {'body': 'Hi Alice, checking now.'}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertTrue(Notification.objects.filter(player_id=self.alice.id, title='Support replied').exists())
        mine = self.alice_api.get('/api/support/messages/').json()['results']
        self.assertEqual((mine[-1]['sender'], mine[-1]['from_staff']), ('Rudo', True))
        self.assertTrue(all(m['read'] for m in mine if not m['from_staff']))
        self.assertEqual(self.bob_api.get('/api/support/messages/').json()['results'], [])

    def test_validation_and_rate_limit(self):
        self.assertEqual(self.alice_api.post('/api/support/messages/', {'body': '  '}, format='json').status_code, 400)
        self.assertEqual(self.alice_api.post('/api/support/messages/', {'body': 'x' * 1001}, format='json').status_code, 400)
        self.alice_api.post('/api/support/messages/', {'body': 'one'}, format='json')
        self.assertIn('Slow down', self.alice_api.post('/api/support/messages/', {'body': 'two'}, format='json').json()['detail'])
