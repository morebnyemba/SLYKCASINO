"""Admin lists that used to stop at a fixed number now page."""
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from apps.wallet.models import WithdrawalRequest


class AdminPagingTests(TestCase):
    def setUp(self):
        self.player = accounts.create_player(username='punter')
        self.api = APIClient()
        self.api.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x' * 12, is_staff=True))

    def test_withdrawals_page_past_200(self):
        WithdrawalRequest.objects.bulk_create([
            WithdrawalRequest(player_id=self.player.id, amount=D('5'), method='ecocash', account_number='0771234567',
                              status='paid', decided_at=timezone.now()) for _ in range(230)])
        first = self.api.get('/api/admin/withdrawals/', {'status': 'paid'}).json()
        self.assertEqual((first['count'], len(first['results'])), (230, 200))       # default unchanged
        last = self.api.get('/api/admin/withdrawals/', {'status': 'paid', 'page_size': 50, 'page': 5}).json()
        self.assertEqual(len(last['results']), 30)
        mine = self.api.get('/api/admin/withdrawals/', {'status': 'all', 'player_id': self.player.id, 'page_size': 50}).json()
        self.assertEqual(mine['count'], 230)

    def test_aviator_bets_page_past_100(self):
        from apps.jet.models import JetBet, JetRound
        rnd = JetRound.objects.create(server_seed='s', seed_hash='h', crash_point=D('1.5'), house_edge_percent=D('3'),
                                      betting_ends_at=timezone.now())
        JetBet.objects.bulk_create([JetBet(round=rnd, player_id=self.player.id, display_name='p***r', slot=i + 1,
                                           stake=D('1'), wallet='deposit', status='lost') for i in range(130)])
        first = self.api.get('/api/admin/jet/bets/', {'player_id': self.player.id}).json()
        self.assertEqual((first['count'], len(first['results'])), (130, 100))
        page3 = self.api.get('/api/admin/jet/bets/', {'player_id': self.player.id, 'page_size': 50, 'page': 3}).json()
        self.assertEqual(len(page3['results']), 30)
        self.assertEqual(first['summary']['bets'], 130)
