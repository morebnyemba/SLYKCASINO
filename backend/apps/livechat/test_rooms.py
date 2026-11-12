"""Group chat: who can read which room, posting rules, and staff moderation
(hide, unhide, delete, pin, mute) — players never see what staff hid."""
from __future__ import annotations

import secrets
from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services as accounts
from apps.accounts.models import AuditLog
from apps.affiliates import services as affiliates
from apps.affiliates.models import Affiliate
from apps.livechat import rooms
from apps.livechat.models import ChatMute, ChatRoom, RoomMessage


def player(name):
    return accounts.register_player(username=name, email=f'{name}@example.com', password=secrets.token_urlsafe(16), currency='USD')


def api_for(p):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f'Bearer {RefreshToken.for_user(p.user).access_token}')
    return client


class Base(TestCase):
    def setUp(self):
        self.alice, self.bob, self.agent = player('alice'), player('bob'), player('agentx')
        aff = affiliates.apply(player_id=self.agent.id, code='AGENTX')
        affiliates.set_status(aff.id, Affiliate.Status.ACTIVE)
        self.a, self.b, self.g = api_for(self.alice), api_for(self.bob), api_for(self.agent)
        self.staff = APIClient()
        self.staff.force_authenticate(User.objects.create_user('mod', 'm@example.com', 'x', is_staff=True))
        self.community = ChatRoom.objects.get(slug='community')
        ChatRoom.objects.filter(pk=self.community.pk).update(slow_mode_seconds=0)

    def say(self, client, text, slug='community', **extra):
        return client.post(f'/api/chat/rooms/{slug}/messages/', {'body': text, **extra}, format='json')

    def read(self, client, slug='community', **params):
        return client.get(f'/api/chat/rooms/{slug}/messages/', params).json()

    def moderate(self, ids, action, **extra):
        return self.staff.post('/api/admin/chat/moderate/', {'ids': ids, 'action': action, **extra}, format='json')


class AudienceTests(Base):
    def test_default_rooms_and_who_sees_them(self):
        slugs = lambda client: [r['slug'] for r in client.get('/api/chat/rooms/').json()['results']]  # noqa: E731
        self.assertEqual(slugs(self.a), ['announcements', 'community'])
        self.assertEqual(slugs(self.g), ['announcements', 'community', 'agents'])
        self.assertEqual([r['slug'] for r in self.staff.get('/api/admin/chat/rooms/').json()['results']],
                         ['announcements', 'community', 'agents', 'staff'])
        self.assertEqual(self.g.get('/api/chat/rooms/').json()['me']['role'], 'agent')
        self.assertEqual(APIClient().get('/api/chat/rooms/').status_code, 401)

    def test_players_cannot_read_or_post_in_rooms_that_are_not_theirs(self):
        for slug in ('agents', 'staff'):
            self.assertEqual(self.a.get(f'/api/chat/rooms/{slug}/messages/').status_code, 404)
            self.assertEqual(self.say(self.a, 'let me in', slug).status_code, 404)
        self.assertEqual(self.say(self.g, 'agents only', 'agents').status_code, 201)
        self.assertEqual(self.g.get('/api/chat/rooms/staff/messages/').status_code, 404)

    def test_only_staff_post_announcements_and_closed_rooms_disappear(self):
        self.assertEqual(self.say(self.a, 'hello', 'announcements').status_code, 403)
        room = ChatRoom.objects.get(slug='announcements')
        self.assertEqual(self.staff.post(f'/api/admin/chat/rooms/{room.id}/messages/', {'body': 'Bonus weekend!'}, format='json').status_code, 201)
        row = self.read(self.a, 'announcements')['results'][0]
        self.assertEqual((row['role'], row['from_staff'], row['sender']), ('staff', True, 'mod'))
        self.staff.patch(f'/api/admin/chat/rooms/{self.community.id}/', {'is_open': False}, format='json')
        self.assertEqual(self.a.get('/api/chat/rooms/community/messages/').status_code, 404)


class PostingTests(Base):
    def test_messages_replies_roles_and_unread(self):
        first = self.say(self.a, '  Who   is winning   tonight? ').json()
        self.assertEqual((first['body'], first['mine'], first['role']), ('Who is winning tonight?', True, 'player'))
        self.assertEqual(self.b.get('/api/chat/rooms/').json()['results'][1]['unread'], 1)
        reply = self.say(self.g, 'Arsenal, easily', reply_to=first['id']).json()
        self.assertEqual((reply['role'], reply['reply_to']['sender']), ('agent', 'alice'))
        seen = self.read(self.b)
        self.assertEqual([m['body'] for m in seen['results']], ['Who is winning tonight?', 'Arsenal, easily'])
        self.assertFalse(seen['results'][0]['mine'])
        self.assertEqual(self.b.get('/api/chat/rooms/').json()['results'][1]['unread'], 0)   # reading marked it read
        self.assertEqual(self.read(self.b, after=reply['id'])['results'], [])                # polling: nothing new

    def test_limits(self):
        self.assertEqual(self.say(self.a, '   ').status_code, 400)
        self.assertEqual(self.say(self.a, 'x' * 501).status_code, 400)
        self.assertEqual(self.say(self.a, 'same thing').status_code, 201)
        self.assertEqual(self.say(self.a, 'Same Thing').status_code, 429)                    # a repeat
        ChatRoom.objects.filter(pk=self.community.pk).update(slow_mode_seconds=30)
        self.assertEqual(self.say(self.a, 'too fast').status_code, 429)
        self.assertEqual(self.say(self.b, 'my first').status_code, 201)                      # slow mode is per person

    def test_suspended_players_cannot_post(self):
        accounts.suspend_player(self.alice.id, reason='test')
        self.assertIn(self.say(self.a, 'hello').status_code, (401, 403))
        self.assertEqual(RoomMessage.objects.count(), 0)


class ModerationTests(Base):
    def setUp(self):
        super().setUp()
        self.bad = self.say(self.a, 'call me on 0771234567').json()['id']
        self.ok = self.say(self.b, 'good luck all').json()['id']

    def test_hide_takes_it_out_of_view_for_players_only_and_can_be_undone(self):
        self.assertEqual(self.moderate([self.bad], 'hide', reason='Phone number').json()['done'], 1)
        self.assertEqual([m['id'] for m in self.read(self.b)['results']], [self.ok])
        self.assertEqual([m['id'] for m in self.read(self.a)['results']], [self.ok])          # the sender too
        staff_view = self.staff.get(f'/api/admin/chat/rooms/{self.community.id}/messages/').json()['results']
        hidden = next(m for m in staff_view if m['id'] == self.bad)
        self.assertEqual((hidden['hidden'], hidden['hidden_by'], hidden['hidden_reason']), (True, 'mod', 'Phone number'))
        only = self.staff.get(f'/api/admin/chat/rooms/{self.community.id}/messages/', {'only': 'hidden'}).json()['results']
        self.assertEqual([m['id'] for m in only], [self.bad])
        self.moderate([self.bad], 'unhide')
        self.assertEqual(len(self.read(self.b)['results']), 2)
        self.assertTrue(AuditLog.objects.filter(event_type='chat_message_hidden', player_id=self.alice.id).exists())

    def test_a_reply_to_a_hidden_message_does_not_leak_it(self):
        reply = self.say(self.b, 'do not post numbers', reply_to=self.bad).json()['id']
        self.moderate([self.bad], 'hide')
        row = next(m for m in self.read(self.a)['results'] if m['id'] == reply)
        self.assertEqual(row['reply_to']['body'], '')

    def test_delete_removes_it_for_good_and_keeps_no_copy_of_the_words(self):
        self.assertEqual(self.moderate([self.bad, self.ok], 'delete').json()['done'], 2)
        self.assertEqual(RoomMessage.objects.count(), 0)
        log = AuditLog.objects.get(event_type='chat_message_deleted', player_id=self.alice.id)
        self.assertEqual((log.metadata['sender'], log.metadata['by']), ('alice', 'mod'))
        self.assertNotIn('0771234567', str(log.metadata))

    def test_pin_shows_at_the_top_until_hidden(self):
        self.moderate([self.ok], 'pin')
        self.assertEqual([m['id'] for m in self.read(self.a)['pinned']], [self.ok])
        self.moderate([self.ok], 'hide')
        self.assertEqual(self.read(self.a)['pinned'], [])

    def test_mute_stops_posting_but_not_reading_and_expires(self):
        res = self.staff.post('/api/admin/chat/mutes/', {'player_id': self.alice.id, 'minutes': 30, 'reason': 'Spam'}, format='json')
        self.assertEqual(res.status_code, 201)
        self.assertEqual(self.say(self.a, 'can I talk?').status_code, 403)
        self.assertEqual(len(self.read(self.a)['results']), 2)
        self.assertTrue(self.a.get('/api/chat/rooms/').json()['me']['muted'])
        self.assertEqual(self.say(self.b, 'still here').status_code, 201)
        ChatMute.objects.filter(player_id=self.alice.id).update(until=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.say(self.a, 'back again').status_code, 201)
        self.staff.post('/api/admin/chat/mutes/', {'player_id': self.bob.id}, format='json')      # until lifted
        self.assertEqual(self.say(self.b, 'hello?').status_code, 403)
        self.assertEqual(self.staff.delete(f'/api/admin/chat/mutes/{self.bob.id}/').json()['mutes'], [])
        self.assertEqual(self.say(self.b, 'thanks').status_code, 201)

    def test_reports_reach_staff_once_per_player(self):
        url = f'/api/chat/messages/{self.bad}/report/'
        self.assertEqual(self.b.post(url, {'reason': 'phone number'}, format='json').status_code, 200)
        self.b.post(url, {}, format='json')
        self.g.post(url, {}, format='json')
        self.assertEqual(self.a.post(url, {}, format='json').status_code, 400)                  # your own
        self.assertEqual(RoomMessage.objects.get(pk=self.bad).reports, 2)
        reported = self.staff.get(f'/api/admin/chat/rooms/{self.community.id}/messages/', {'only': 'reported'}).json()['results']
        self.assertEqual([m['id'] for m in reported], [self.bad])
        rows = self.staff.get('/api/admin/chat/rooms/').json()['results']
        self.assertEqual(next(r for r in rows if r['slug'] == 'community')['reported'], 1)

    def test_players_cannot_moderate(self):
        self.assertEqual(self.a.post('/api/admin/chat/moderate/', {'ids': [self.ok], 'action': 'delete'}, format='json').status_code, 403)
        self.assertEqual(self.a.post('/api/admin/chat/mutes/', {'player_id': self.bob.id}, format='json').status_code, 403)
        self.assertEqual(self.a.get('/api/admin/chat/rooms/').status_code, 403)
        self.assertEqual(RoomMessage.objects.count(), 2)

    def test_rooms_can_be_created_edited_and_deleted_by_a_superuser(self):
        res = self.staff.post('/api/admin/chat/rooms/', {'name': 'VIP Lounge', 'audience': 'everyone', 'slow_mode_seconds': 10}, format='json')
        self.assertEqual((res.status_code, res.json()['slug']), (201, 'vip-lounge'))
        room_id = res.json()['id']
        self.assertEqual(self.staff.patch(f'/api/admin/chat/rooms/{room_id}/', {'audience': 'nobody'}, format='json').status_code, 400)
        self.assertEqual(self.staff.delete(f'/api/admin/chat/rooms/{room_id}/').status_code, 403)
        boss = APIClient()
        boss.force_authenticate(User.objects.create_superuser('boss', 'b@example.com', 'x'))
        self.assertEqual(boss.delete(f'/api/admin/chat/rooms/{room_id}/').status_code, 204)

    def test_deleting_an_account_removes_their_chat(self):
        rooms.mute(player_id=self.alice.id, by='mod')
        from apps.livechat import services
        services.erase_player_data(self.alice.id)
        self.assertEqual(list(RoomMessage.objects.values_list('id', flat=True)), [self.ok])
        self.assertFalse(ChatMute.objects.exists())
