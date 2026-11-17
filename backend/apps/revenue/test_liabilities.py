"""Money owed: players, agents and partners, from the live balances."""
from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from apps.affiliates import services as affiliates
from apps.affiliates.models import Affiliate, Commission, Payout
from apps.revenue import liabilities
from apps.revenue.models import ShareEntry, ShareWallet, ShareWithdrawal
from apps.wallet import services as wallet
from apps.wallet.models import BonusRollover, WithdrawalRequest


@override_settings(REVENUE_SHARE_CONTROLLER_IDS=[])   # user ids depend on creation order
class _Base(TestCase):
    def setUp(self):
        self.p1 = accounts.create_player(username='p1')
        self.p2 = accounts.create_player(username='p2')
        for p, dep, win, bonus in ((self.p1, '10', '25', '3'), (self.p2, '4', '0', '0')):
            wallet.ensure_wallet(p.id)
            wallet.credit(player_id=p.id, amount=D(dep), kind='deposit', idempotency_key=f'd{p.id}')
            if D(win):
                wallet.credit(player_id=p.id, amount=D(win), kind='bet_payout', bucket='winnings', idempotency_key=f'w{p.id}')
            if D(bonus):
                wallet.credit(player_id=p.id, amount=D(bonus), kind='bonus', idempotency_key=f'b{p.id}')
        WithdrawalRequest.objects.create(player_id=self.p1.id, amount=D('10'), fee=D('0.50'))
        BonusRollover.objects.filter(player_id=self.p1.id).update(aviator_profit=D('1.25'))


@override_settings(REVENUE_SHARE_CONTROLLER_IDS=[])
class LiabilitiesTests(_Base):
    def test_players(self):
        p = liabilities.players()
        self.assertEqual((p['winnings'], p['deposit'], p['withdrawals_waiting'], p['withdrawals_waiting_count']),
                         ('25.00', '14.00', '9.50', 1))
        self.assertEqual(p['total'], '48.50')                         # 25 + 14 + 9.50 to send
        self.assertEqual((p['deposit_after_fee'], p['bonus'], p['aviator_bonus_profit']), ('7.00', '3.00', '1.25'))
        self.assertEqual(p['players_with_cash'], 2)

    def test_agents_and_what_they_owe_back(self):
        ag = accounts.create_player(username='agent')
        a = affiliates.apply(player_id=ag.id, code='AGT1')
        affiliates.set_status(a.id, Affiliate.Status.ACTIVE)
        Commission.objects.create(affiliate=a, kind=Commission.Kind.NET_LOSS, amount=D('6'), status=Commission.Status.APPROVED)
        Commission.objects.create(affiliate=a, kind=Commission.Kind.NET_LOSS, amount=D('2'), status=Commission.Status.PENDING)
        Payout.objects.create(affiliate=a, amount=D('1.50'), method=Payout.Method.ECOCASH, status=Payout.Status.REQUESTED)
        out = liabilities.agents()
        self.assertEqual(out['total'], '6.00')                        # 4.50 unpaid + 1.50 being sent
        self.assertEqual((out['in_payout'], out['pending_approval'], out['agents_with_money']), ('1.50', '2.00', 1))
        ag2 = accounts.create_player(username='agent2')
        b = affiliates.apply(player_id=ag2.id, code='AGT2')
        Payout.objects.create(affiliate=b, amount=D('0.70'), method=Payout.Method.WALLET, status=Payout.Status.PAID)
        self.assertEqual(liabilities.agents()['owed_by_agents'], '0.70')

    def test_partners_and_api_visibility(self):
        ShareWallet.ensure()
        w = ShareWallet.objects.get(slot=1)
        ShareEntry.objects.create(wallet=w, kind=ShareEntry.Kind.ACCRUAL, amount=D('40'))
        req = ShareWithdrawal.objects.create(wallet=w, amount=D('15'), method='ecocash', requested_by='x')
        ShareEntry.objects.create(wallet=w, kind=ShareEntry.Kind.WITHDRAWAL, amount=D('-15'), withdrawal=req)
        part = liabilities.partners()
        self.assertEqual((part['balances'], part['withdrawals_waiting'], part['total']), ('25.00', '15.00', '40.00'))
        staff = APIClient()
        staff.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))
        body = staff.get('/api/admin/liabilities/').json()
        self.assertIsNone(body['partners'])                           # not allowed to see the revenue share
        self.assertEqual(body['total'], '48.50')
        boss = APIClient()
        boss.force_authenticate(User.objects.create_superuser('boss', 'b@example.com', 'x'))
        body = boss.get('/api/admin/liabilities/').json()
        self.assertEqual((body['partners']['total'], body['total']), ('40.00', '88.50'))
        self.assertEqual(APIClient().get('/api/admin/liabilities/').status_code, 401)


@override_settings(REVENUE_SHARE_CONTROLLER_IDS=[])
class OwedDetailTests(_Base):
    """Who is owed, person by person, and how many people."""

    def test_players_list_biggest_first_with_headcount_and_search(self):
        self.assertEqual(liabilities.players()['people'], 2)
        out = liabilities.player_rows()
        self.assertEqual((out['count'], out['total']), (2, '48.50'))
        first = out['results'][0]
        self.assertEqual((first['username'], first['winnings'], first['deposit'], first['withdrawals_waiting'],
                          first['total'], first['bonus'], first['aviator_bonus_profit']),
                         ('p1', '25.00', '10.00', '9.50', '44.50', '3.00', '1.25'))
        self.assertEqual(out['results'][1]['username'], 'p2')
        self.assertEqual(liabilities.player_rows(q='p2')['count'], 1)
        self.assertEqual(len(liabilities.player_rows(page=2, size=1)['results']), 1)

    def test_agents_and_partners_lists_and_access(self):
        ag = accounts.create_player(username='agent')
        a = affiliates.apply(player_id=ag.id, code='AGT1')
        Commission.objects.create(affiliate=a, kind=Commission.Kind.NET_LOSS, amount=D('6'), status=Commission.Status.APPROVED)
        idle = accounts.create_player(username='idle')
        affiliates.apply(player_id=idle.id, code='IDLE1')                       # owed nothing: not listed
        out = liabilities.agent_rows()
        self.assertEqual((out['count'], out['total'], [r['code'] for r in out['results']]), (1, '6.00', ['AGT1']))
        self.assertEqual(out['results'][0]['username'], 'agent')
        staff = APIClient()
        staff.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))
        self.assertEqual(staff.get('/api/admin/liabilities/players/?q=p1').json()['count'], 1)
        self.assertEqual(staff.get('/api/admin/liabilities/agents/').json()['count'], 1)
        self.assertEqual(staff.get('/api/admin/liabilities/partners/').status_code, 403)
        self.assertEqual(staff.get('/api/admin/liabilities/nope/').status_code, 404)
        boss = APIClient()
        boss.force_authenticate(User.objects.create_superuser('boss', 'b@example.com', 'x'))
        self.assertEqual(boss.get('/api/admin/liabilities/partners/').json()['count'], 0)
