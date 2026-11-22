"""Agent competitions (prizes credited automatically to the locked balance) and
staff adjustments to an agent's locked balance."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from apps.affiliates import competitions, services
from apps.affiliates.models import Affiliate, AffiliateCompetition, Commission, CompetitionAward
from apps.wallet import services as wallet

D = Decimal


class _Base(TestCase):
    def setUp(self):
        self.agent_player = accounts.register_player(username='tendai', email='t@example.com', password='Pass-word-123')
        self.agent = services.apply(player_id=self.agent_player.id, code='TENDAI')
        services.set_status(self.agent.id, Affiliate.Status.ACTIVE)
        self.agent.refresh_from_db()
        self.staff = APIClient()
        self.staff.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))
        self.today = timezone.localdate()

    def customer(self, name, deposit=None):
        p = accounts.create_player(username=name)
        services.attach_referral(player_id=p.id, code='TENDAI')
        if deposit:
            wallet.credit(player_id=p.id, amount=D(deposit), kind='deposit', idempotency_key=f'dep:{name}')
        return p

    def comp(self, **kw):
        values = {'name': 'November sprint', 'starts_on': self.today - timedelta(days=3), 'ends_on': self.today + timedelta(days=7),
                  'target_customers': 3, 'prize': D('25')}
        values.update(kw)
        return AffiliateCompetition.objects.create(**values)


class CompetitionTests(_Base):
    def test_reaching_the_customer_target_pays_the_prize_once(self):
        c = self.comp()
        self.customer('a', '5'); self.customer('b', '5')
        self.assertEqual(competitions.award_due(), 0)
        self.assertEqual(competitions.progress(c, self.agent)['percent'], 67)
        self.customer('c', '5')
        self.assertEqual(competitions.award_due(), 1)
        self.assertEqual(competitions.award_due(), 0)                         # never twice
        award = CompetitionAward.objects.get()
        self.assertEqual((award.commission.kind, award.commission.amount, award.commission.status), ('prize', D('25.00'), 'approved'))
        self.assertEqual(services.balance(self.agent)['available'] + services.balance(self.agent)['locked'], D('25.00'))
        from apps.notifications.models import Notification
        self.assertTrue(Notification.objects.filter(player_id=self.agent_player.id, title__contains='November sprint').exists())

    def test_deposit_target_and_both_targets(self):
        c = self.comp(target_customers=2, target_deposits=D('100'))
        self.customer('a', '60'); self.customer('b', '30')                      # 2 customers but $90
        self.assertEqual(competitions.award_due(), 0)
        old = self.customer('c')
        wallet.credit(player_id=old.id, amount=D('10'), kind='deposit', idempotency_key='dep:c2')
        prog = competitions.progress(c, self.agent)
        self.assertEqual((prog['customers'], prog['deposits'], prog['reached']), (3, '100.00', True))
        self.assertEqual(competitions.award_due(), 1)

    def test_fake_sign_ups_dont_count_with_a_minimum_deposit(self):
        c = self.comp(min_customer_deposit=D('2'))
        for name in ('a', 'b', 'c', 'd'):
            self.customer(name)                                                 # signed up, never deposited
        self.customer('e', '1')                                                 # below the minimum
        self.assertEqual(competitions.progress(c, self.agent)['customers'], 0)
        for name in ('f', 'g', 'h'):
            self.customer(name, '2')
        self.assertEqual(competitions.award_due(), 1)

    def test_outside_the_window_or_switched_off_nothing_is_paid(self):
        self.comp(starts_on=self.today + timedelta(days=1))                   # not started
        self.comp(name='Old', starts_on=self.today - timedelta(days=30), ends_on=self.today - timedelta(days=5))
        self.comp(name='Off', active=False)
        for name in ('a', 'b', 'c'):
            self.customer(name, '5')
        self.assertEqual(competitions.award_due(), 0)

    def test_agent_sees_competitions_with_progress(self):
        self.comp()
        self.customer('a', '5')
        api = APIClient()
        api.force_authenticate(self.agent_player.user)
        [row] = api.get('/api/affiliates/me/competitions/').json()['competitions']
        self.assertEqual((row['name'], row['status'], row['my']['customers'], row['won'], row['prize']),
                         ('November sprint', 'running', 1, False, '25.00'))
        for name in ('b', 'c'):
            self.customer(name, '5')
        [row] = api.get('/api/affiliates/me/competitions/').json()['competitions']   # the page load awards it
        self.assertTrue(row['won'])

    def test_admin_creates_edits_and_sees_standings(self):
        body = {'name': 'Deposit race', 'starts_on': str(self.today), 'ends_on': str(self.today + timedelta(days=5)),
                'target_deposits': '50', 'prize': '10'}
        res = self.staff.post('/api/admin/affiliate-competitions/', body, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        cid = res.json()['id']
        for bad, word in (({**body, 'target_deposits': '0'}, 'target'), ({**body, 'prize': '0'}, 'prize'),
                          ({**body, 'ends_on': str(self.today - timedelta(days=1))}, 'end date')):
            r = self.staff.post('/api/admin/affiliate-competitions/', bad, format='json')
            self.assertEqual(r.status_code, 400, bad)
            self.assertIn(word, r.json()['detail'])
        self.customer('a', '60')
        detail = self.staff.get(f'/api/admin/affiliate-competitions/{cid}/').json()
        self.assertEqual((detail['winners'], detail['standings'][0]['code'], detail['standings'][0]['won']), (1, 'TENDAI', True))
        r = self.staff.patch(f'/api/admin/affiliate-competitions/{cid}/', {'prize': '20'}, format='json')
        self.assertEqual(r.status_code, 400)                                    # already paid: can't change the prize
        self.assertIn('already paid', r.json()['detail'])
        self.assertFalse(self.staff.patch(f'/api/admin/affiliate-competitions/{cid}/', {'active': False}, format='json').json()['active'])
        self.assertEqual(self.staff.delete(f'/api/admin/affiliate-competitions/{cid}/').status_code, 409)


@pytest.mark.affiliate_lock
class LockedBalanceTests(_Base):
    def test_prize_lands_in_the_locked_balance(self):
        self.comp()
        for name in ('a', 'b', 'c'):
            self.customer(name, '5')
        competitions.award_due()
        bal = services.balance(self.agent)
        self.assertEqual((bal['locked'], bal['available']), (D('25.00'), D('0.00')))

    def test_staff_add_and_take_from_the_locked_balance(self):
        url = f'/api/admin/affiliates/{self.agent.id}/adjust-locked/'
        body = self.staff.post(url, {'amount': '40', 'reason': 'Top agent bonus'}, format='json').json()
        self.assertEqual(body['locked'], '40.00')
        body = self.staff.post(url, {'amount': '-15', 'reason': 'Correction'}, format='json').json()
        self.assertEqual(body['locked'], '25.00')
        res = self.staff.post(url, {'amount': '-30', 'reason': 'Too much'}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('at most', res.json()['detail'])
        self.assertEqual(self.staff.post(url, {'amount': '5', 'reason': ''}, format='json').status_code, 400)
        rows = list(Commission.objects.filter(kind='adjust').values_list('amount', 'note'))
        self.assertEqual(sorted(rows), [(D('-15.00'), 'Correction'), (D('40.00'), 'Top agent bonus')])
        from apps.accounts.models import AuditLog
        self.assertEqual(AuditLog.objects.filter(event_type='affiliate_balance_adjusted').count(), 2)
