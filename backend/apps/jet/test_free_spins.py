from datetime import timedelta
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from apps.accounts.models import Player
from apps.jet import free_spins, social
from apps.jet.models import JetFreeBet


class FreeSpinTests(TestCase):
    def setUp(self):
        self.a = accounts.register_player(username='ann', email='a@example.com', password='Pass-word-123')
        self.b = accounts.register_player(username='ben', email='b@example.com', password='Pass-word-123')
        self.s = accounts.register_player(username='sus', email='s@example.com', password='Pass-word-123')
        Player.objects.filter(pk=self.s.pk).update(is_suspended=True)
        self.boss, self.clerk = APIClient(), APIClient()
        self.boss.force_authenticate(User.objects.create_superuser('boss', 'boss@example.com', 'x'))
        self.clerk.force_authenticate(User.objects.create_user('clerk', 'c@example.com', 'x', is_staff=True))

    def player(self, p):
        c = APIClient()
        c.force_authenticate(p.user)
        return c

    def test_give_claim_and_they_become_free_bets(self):
        res = self.boss.post('/api/admin/jet/free-spins/', {'audience': 'all', 'amount': '1', 'count': 3, 'days': 7,
                                                            'message': 'Weekend spins'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual((res.json()['players'], res.json()['spins']), (2, 6))             # suspended player left out
        self.assertEqual(social.free_bets_for(self.a.id), [])                                # not usable until claimed
        offers = self.player(self.a).get('/api/jet/free-spins/').json()['offers']
        self.assertEqual((offers[0]['count'], offers[0]['amount'], offers[0]['message']), (3, '1.00', 'Weekend spins'))
        out = self.player(self.a).post('/api/jet/free-spins/', {}, format='json').json()
        self.assertEqual((out['claimed'], out['offers'], len(out['free_bets'])), (3, [], 3))
        self.assertEqual(len(social.free_bets_for(self.b.id)), 0)                           # ben hasn't claimed
        from apps.notifications.models import Notification
        self.assertTrue(Notification.objects.filter(player_id=self.b.id, title__contains='Free Aviator spins').exists())

    def test_chosen_players_and_unknown_names(self):
        res = self.boss.post('/api/admin/jet/free-spins/', {'audience': 'usernames', 'usernames': 'ann, @ghost',
                                                            'amount': '2', 'count': 1, 'days': 1}, format='json').json()
        self.assertEqual((res['players'], res['not_found']), (1, ['ghost']))

    def test_unclaimed_spins_lapse(self):
        g, _ = free_spins.grant(audience='all', amount='1', count=1, days=1, by='boss')
        JetFreeBet.objects.filter(grant=g).update(expires_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(free_spins.offers_for(self.a.id), [])
        self.assertEqual(free_spins.claim(self.a.id), 0)

    def test_limits_and_superusers_only(self):
        for body in ({'amount': '0.01'}, {'amount': '101'}, {'count': 0}, {'count': 51}, {'days': 0}):
            res = self.boss.post('/api/admin/jet/free-spins/', {'audience': 'all', 'amount': '1', 'count': 1, 'days': 1, **body},
                                 format='json')
            self.assertEqual(res.status_code, 400, body)
        self.assertEqual(self.clerk.post('/api/admin/jet/free-spins/', {'audience': 'all', 'amount': '1'}, format='json').status_code, 403)
        self.assertFalse(JetFreeBet.objects.exists())
