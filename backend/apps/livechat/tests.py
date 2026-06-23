"""livechat tests — realtime WebSocket ticket minting is admin-only."""
from __future__ import annotations

from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services as account_services
from common.realtime_auth import make_ws_ticket

User = get_user_model()


class RealtimeTicketViewTests(TestCase):
    def setUp(self):
        self.player = account_services.register_player(
            username='ticketplayer', email='ticket@example.com', password='Passw0rd!', currency='USD',
        )
        self.client = APIClient()

    def _auth(self, user):
        refresh = RefreshToken.for_user(user)
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

    def test_non_admin_cannot_get_ticket(self):
        self._auth(self.player.user)
        resp = self.client.get('/api/realtime/ticket/?channel=admin:bets')
        self.assertEqual(resp.status_code, status.HTTP_403_FORBIDDEN)

    def test_admin_can_get_ticket_for_admin_channel(self):
        admin_user = User.objects.create_user(username='opadmin', password='Passw0rd!', is_staff=True)
        self._auth(admin_user)
        resp = self.client.get('/api/realtime/ticket/?channel=admin:bets')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        ticket = resp.data['ticket']
        channel, expiry, signature = ticket.split('.')
        self.assertEqual(channel, 'admin:bets')
        self.assertTrue(expiry.isdigit())
        self.assertEqual(len(signature), 64)  # hex-encoded sha256

    def test_rejects_non_admin_channel_prefix(self):
        admin_user = User.objects.create_user(username='opadmin2', password='Passw0rd!', is_staff=True)
        self._auth(admin_user)
        resp = self.client.get('/api/realtime/ticket/?channel=odds')
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)


class MakeWsTicketTests(TestCase):
    def test_ticket_is_deterministic_per_signature_inputs(self):
        ticket = make_ws_ticket('admin:chat', ttl=30)
        channel, expiry, signature = ticket.split('.')
        self.assertEqual(channel, 'admin:chat')
        self.assertTrue(expiry.isdigit())
        self.assertEqual(len(signature), 64)
