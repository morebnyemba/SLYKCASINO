from datetime import timedelta
from decimal import Decimal as D
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from apps.accounts.models import Player
from apps.promotions import bulk
from apps.promotions.models import BulkGrant, PromotionClaim
from apps.wallet import services as wallet


def bonus(pid):
    return wallet.get_balances(pid)['bonus']


def money(pid):
    b = wallet.get_balances(pid)
    return b['deposit'], b['winnings']


class BulkGrantTests(TestCase):
    def setUp(self):
        self.a = accounts.register_player(username='ann', email='a@example.com', password='Pass-word-123')
        self.b = accounts.register_player(username='ben', email='b@example.com', password='Pass-word-123')
        self.c = accounts.register_player(username='cat', email='c@example.com', password='Pass-word-123')
        self.banned = accounts.register_player(username='sus', email='s@example.com', password='Pass-word-123')
        Player.objects.filter(pk=self.banned.pk).update(is_suspended=True)
        self.out = accounts.register_player(username='exc', email='e@example.com', password='Pass-word-123')
        Player.objects.filter(pk=self.out.pk).update(self_excluded=True)
        wallet.credit(player_id=self.a.id, amount=D('10'), kind='deposit', idempotency_key='dep:a')
        wallet.credit(player_id=self.a.id, amount=D('7'), kind='adjustment', bucket='winnings', idempotency_key='win:a')
        self.boss, self.clerk = APIClient(), APIClient()
        self.boss.force_authenticate(User.objects.create_superuser('boss', 'boss@example.com', 'x'))
        self.clerk.force_authenticate(User.objects.create_user('clerk', 'clerk@example.com', 'x', is_staff=True))

    def go(self, **body):
        with patch('apps.promotions.tasks.run_bulk_grant.delay', side_effect=lambda gid: bulk.run(gid)), \
                self.captureOnCommitCallbacks(execute=True):
            return self.boss.post('/api/admin/bulk-grants/', body, format='json')

    def give(self, amount='5', audience='all', **extra):
        base = {'kind': 'credit', 'audience': audience, 'amount': amount, 'wagering_multiplier': '3', 'name': 'Weekend boost'}
        total = self.boss.post('/api/admin/bulk-grants/', {**base, 'preview': True}, format='json').json()['total']
        return self.go(**base, confirm_total=total, **extra)

    def test_preview_then_give_everyone_a_bonus_but_not_suspended_or_excluded(self):
        p = self.boss.post('/api/admin/bulk-grants/', {'kind': 'credit', 'audience': 'all', 'amount': '5', 'preview': True},
                           format='json').json()
        self.assertEqual((p['players'], p['total']), (3, '15.00'))
        res = self.give()
        self.assertEqual(res.status_code, 201, res.content)
        g = BulkGrant.objects.get()
        self.assertEqual((g.status, g.affected, g.total), ('done', 3, D('15.00')))
        for pl in (self.a, self.b, self.c):
            self.assertEqual(bonus(pl.id), D('5.00'))
        for pl in (self.banned, self.out):
            self.assertEqual(bonus(pl.id), D('0.00'))
        claim = PromotionClaim.objects.get(player_id=self.b.id, promotion__code=f'bulk-{g.pk}')
        self.assertEqual(claim.wagering_required, D('15.00'))            # 3x the bonus
        self.assertEqual(money(self.a.id), (D('10.00'), D('7.00')))       # real money untouched

    def test_running_it_again_pays_nobody_twice(self):
        self.give()
        g = BulkGrant.objects.get()
        BulkGrant.objects.filter(pk=g.pk).update(status='running')
        bulk.run(g.pk)
        self.assertEqual(bonus(self.a.id), D('5.00'))
        self.assertEqual(BulkGrant.objects.get(pk=g.pk).total, D('15.00'))

    def test_audiences(self):
        self.give(audience='depositors')
        self.assertEqual((bonus(self.a.id), bonus(self.b.id)), (D('5.00'), D('0.00')))

    def test_the_total_must_be_typed_back(self):
        res = self.go(kind='credit', audience='all', amount='5', name='Boost', confirm_total='1.50')
        self.assertEqual(res.status_code, 400)
        self.assertIn('$15.00', res.json()['detail'])
        self.assertFalse(BulkGrant.objects.exists())

    def test_limits_and_name(self):
        for body, why in (({'amount': '0'}, 'between'), ({'amount': '501'}, 'between'), ({'name': ''}, 'name')):
            res = self.go(**{'kind': 'credit', 'audience': 'all', 'amount': '5', 'name': 'X', 'confirm_total': '15.00', **body})
            self.assertEqual(res.status_code, 400, body)
            self.assertIn(why, res.json()['detail'])

    def test_take_back_only_from_bonus_and_never_below_zero(self):
        self.give(amount='5')
        wallet.debit(player_id=self.b.id, amount=D('3'), kind='bet_stake', bucket='bonus', idempotency_key='b:bet')
        p = self.boss.post('/api/admin/bulk-grants/', {'kind': 'debit', 'audience': 'all', 'amount': '4', 'preview': True},
                           format='json').json()
        self.assertEqual(p['total'], '10.00')                             # a: 4, b: only 2 left, c: 4
        self.go(kind='debit', audience='all', amount='4', name='Correction', confirm_total='10.00')
        self.assertEqual((bonus(self.a.id), bonus(self.b.id), bonus(self.c.id)), (D('1.00'), D('0.00'), D('1.00')))
        self.assertEqual(money(self.a.id), (D('10.00'), D('7.00')))

    def test_undo_takes_back_what_is_left(self):
        self.give(amount='5')
        g = BulkGrant.objects.get()
        wallet.debit(player_id=self.c.id, amount=D('5'), kind='bet_stake', bucket='bonus', idempotency_key='c:bet')
        with patch('apps.promotions.tasks.run_bulk_grant.delay', side_effect=lambda gid: bulk.run(gid)), \
                self.captureOnCommitCallbacks(execute=True):
            res = self.boss.post(f'/api/admin/bulk-grants/{g.pk}/', {'action': 'undo'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        u = BulkGrant.objects.get(undo_of=g)
        self.assertEqual((u.status, u.affected, u.total), ('done', 2, D('10.00')))
        self.assertEqual((bonus(self.a.id), bonus(self.c.id)), (D('0.00'), D('0.00')))
        self.assertFalse(PromotionClaim.objects.filter(promotion__code=f'bulk-{g.pk}', status='active').exists())
        again = self.boss.post(f'/api/admin/bulk-grants/{g.pk}/', {'action': 'undo'}, format='json')
        self.assertIn('already been undone', again.json()['detail'])

    def test_one_at_a_time_and_resume_when_stalled(self):
        with patch('apps.promotions.tasks.run_bulk_grant.delay'), self.captureOnCommitCallbacks(execute=True):
            self.boss.post('/api/admin/bulk-grants/', {'kind': 'credit', 'audience': 'all', 'amount': '1', 'name': 'A',
                                                       'confirm_total': '3.00'}, format='json')   # queued, worker never runs it
        g = BulkGrant.objects.get()
        res = self.go(kind='credit', audience='all', amount='1', name='B', confirm_total='3.00')
        self.assertIn('still running', res.json()['detail'])
        self.assertIn('not stuck', self.boss.post(f'/api/admin/bulk-grants/{g.pk}/', {'action': 'resume'}, format='json').json()['detail'])
        BulkGrant.objects.filter(pk=g.pk).update(heartbeat_at=timezone.now() - timedelta(minutes=10))
        self.assertTrue(self.boss.get(f'/api/admin/bulk-grants/{g.pk}/').json()['stalled'])
        with patch('apps.promotions.tasks.run_bulk_grant.delay', side_effect=lambda gid: bulk.run(gid)), \
                self.captureOnCommitCallbacks(execute=True):
            self.boss.post(f'/api/admin/bulk-grants/{g.pk}/', {'action': 'resume'}, format='json')
        self.assertEqual((BulkGrant.objects.get(pk=g.pk).status, bonus(self.b.id)), ('done', D('1.00')))

    def test_superusers_only(self):
        self.assertEqual(self.clerk.get('/api/admin/bulk-grants/').status_code, 403)
        self.assertEqual(self.clerk.post('/api/admin/bulk-grants/', {'kind': 'credit', 'preview': True}, format='json').status_code, 403)
