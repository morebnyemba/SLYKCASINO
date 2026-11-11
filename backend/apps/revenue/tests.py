"""House revenue share: three partner wallets taking 10% of each day's GGR,
losses carried forward, a wallet resetting on its own withdrawal, and the 70%
operating pool paying affiliates and recorded costs."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal as D
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog
from apps.revenue import services
from apps.revenue.models import RevenueDay, RevenueSettings, ShareEntry, ShareWallet, ShareWithdrawal

URL = '/api/admin/revenue-share/'


class SplitTests(TestCase):
    def test_a_winning_day_shares_ten_percent_each_and_pools_the_rest(self):
        self.assertEqual(services.split(D('1000.00'), D('0'), D('10')),
                         {'base': D('1000.00'), 'carry_out': D('0'), 'share_each': D('100.00'), 'pool': D('700.00')})

    def test_a_losing_day_shares_nothing_and_carries_the_loss(self):
        self.assertEqual(services.split(D('-300.00'), D('0'), D('10')),
                         {'base': D('0'), 'carry_out': D('-300.00'), 'share_each': D('0.00'), 'pool': D('0.00')})

    def test_a_carried_loss_is_earned_back_first(self):
        self.assertEqual(services.split(D('200.00'), D('-300.00'), D('10'))['carry_out'], D('-100.00'))
        maths = services.split(D('500.00'), D('-300.00'), D('10'))
        self.assertEqual((maths['base'], maths['share_each'], maths['pool'], maths['carry_out']),
                         (D('200.00'), D('20.00'), D('140.00'), D('0')))

    def test_shares_round_down_and_the_pool_keeps_the_cents(self):
        maths = services.split(D('100.07'), D('0'), D('10'))
        self.assertEqual((maths['share_each'], maths['pool']), (D('10.00'), D('70.07')))


class Base(TestCase):
    def setUp(self):
        self.today = timezone.localdate()
        cfg = RevenueSettings.load()
        cfg.started_on = self.today - timedelta(days=4)
        cfg.save()
        self.boss = User.objects.create_superuser('boss', 'b@example.com', 'x')
        self.partners = [User.objects.create_user(f'p{i}', f'p{i}@example.com', 'x', is_staff=True) for i in (1, 2, 3)]
        services.update_settings(wallets=[{'slot': i + 1, 'holder_id': u.id} for i, u in enumerate(self.partners)], by='boss')
        self.wallets = list(ShareWallet.objects.order_by('slot'))

    def api(self, user):
        client = APIClient()
        client.force_authenticate(user)
        return client

    def close(self, ggrs):
        """Close the four days before today with these GGRs, oldest first."""
        by_day = {self.today - timedelta(days=4 - i): D(g) for i, g in enumerate(ggrs)}
        with patch.object(services, 'day_ggr', side_effect=lambda day: by_day[day]):
            return services.close_days(today=self.today)

    def balance(self, i):
        return services.wallet_balance(self.wallets[i])


class CloseDayTests(Base):
    def test_closes_each_completed_day_once_in_order_with_losses_carried(self):
        self.assertEqual(self.close(['1000', '-300', '200', '500']), 4)
        days = {d.day: d for d in RevenueDay.objects.all()}
        first, losing, short, back = (days[self.today - timedelta(days=n)] for n in (4, 3, 2, 1))
        self.assertEqual((first.share_each, first.pool), (D('100.00'), D('700.00')))
        self.assertEqual((losing.share_each, losing.carry_out), (D('0.00'), D('-300.00')))
        self.assertEqual((short.share_each, short.carry_out), (D('0.00'), D('-100.00')))   # 200 earns back part of it
        self.assertEqual((back.base, back.share_each, back.pool), (D('400.00'), D('40.00'), D('280.00')))
        for i in range(3):
            self.assertEqual(self.balance(i), D('140.00'))
        self.assertFalse(RevenueDay.objects.filter(day=self.today).exists())   # today isn't over
        self.assertEqual(self.close(['1', '1', '1', '1']), 0)                   # never twice
        self.assertEqual(self.balance(0), D('140.00'))

    def test_days_before_the_start_date_never_count(self):
        self.close(['10', '10', '10', '10'])
        self.assertEqual(RevenueDay.objects.order_by('day').first().day, self.today - timedelta(days=4))

    def test_an_unassigned_wallet_still_accrues(self):
        services.update_settings(wallets=[{'slot': 3, 'holder_id': None}], by='boss')
        self.close(['1000', '0', '0', '0'])
        self.assertEqual(self.balance(2), D('100.00'))

    def test_the_share_percent_applies_to_days_not_yet_closed(self):
        with patch.object(services, 'day_ggr', return_value=D('1000')):
            services.close_days(today=self.today - timedelta(days=2))    # closes 2 days at 10%
            services.update_settings(share_percent='5', by='boss')
            services.close_days(today=self.today)                         # the last 2 at 5%
        self.assertEqual(self.balance(0), D('300.00'))

    def test_ggr_comes_from_the_player_ledger(self):
        from apps.accounts import services as accounts
        from apps.wallet import services as wallet
        player = accounts.create_player(username='punter')
        wallet.credit(player_id=player.id, amount=D('100'), kind='deposit', idempotency_key='g:d')
        wallet.debit(player_id=player.id, amount=D('50'), kind='bet_stake', bucket='deposit', idempotency_key='g:s')
        wallet.credit(player_id=player.id, amount=D('20'), kind='bet_payout', bucket='deposit', idempotency_key='g:w')
        self.assertEqual(services.day_ggr(self.today), D('30.00'))
        self.assertEqual(services.today_so_far()['share_each'], '3.00')


class WithdrawalTests(Base):
    def setUp(self):
        super().setUp()
        self.close(['1000', '0', '0', '0'])

    def test_the_holder_takes_the_whole_balance_and_only_their_wallet_resets(self):
        res = self.api(self.partners[0]).post(URL + 'withdraw/', {'method': 'ecocash', 'account': '0771234567'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()['amount'], '100.00')
        self.assertEqual((self.balance(0), self.balance(1), self.balance(2)), (D('0.00'), D('100.00'), D('100.00')))
        self.assertEqual(self.api(self.partners[0]).post(URL + 'withdraw/', {'method': 'ecocash', 'account': '0771234567'},
                                                         format='json').status_code, 400)   # one at a time

    def test_paid_stays_reset_and_new_days_start_from_zero(self):
        w = services.request_withdrawal(user=self.partners[0], method='bank', account='Steward 12345')
        res = self.api(self.boss).post(URL + f'withdrawals/{w.id}/decide/', {'decision': 'paid', 'reference': 'TX9'}, format='json')
        self.assertEqual(res.json()['status'], 'paid')
        with patch.object(services, 'day_ggr', return_value=D('500')):
            services.close_days(today=self.today + timedelta(days=1))   # today closes too
        self.assertEqual(self.balance(0), D('50.00'))
        self.assertEqual(self.balance(1), D('150.00'))

    def test_a_rejected_withdrawal_goes_back_into_the_wallet(self):
        w = services.request_withdrawal(user=self.partners[1], method='cash')
        services.decide_withdrawal(w.id, decision='rejected', by='boss', note='Ask again on Friday')
        self.assertEqual(self.balance(1), D('100.00'))
        self.assertEqual(ShareEntry.objects.filter(withdrawal=w).count(), 2)
        with self.assertRaises(services.RevenueError):
            services.decide_withdrawal(w.id, decision='paid', by='boss')

    def test_rules(self):
        stranger = User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True)
        with self.assertRaisesMessage(services.RevenueError, 'don’t hold'):
            services.request_withdrawal(user=stranger, method='cash')
        with self.assertRaisesMessage(services.RevenueError, 'number or account'):
            services.request_withdrawal(user=self.partners[0], method='ecocash', account='')
        services.request_withdrawal(user=self.partners[0], method='cash')
        services.decide_withdrawal(ShareWithdrawal.objects.get().id, decision='paid', by='boss')
        with self.assertRaisesMessage(services.RevenueError, 'nothing to withdraw'):
            services.request_withdrawal(user=self.partners[0], method='cash')


class PoolTests(Base):
    def test_pool_pays_affiliates_and_recorded_costs(self):
        from apps.accounts import services as accounts
        from apps.affiliates import services as affiliates
        from apps.affiliates.models import Commission
        partner = accounts.create_player(username='agent')
        affiliate = affiliates.apply(player_id=partner.id, code='AGENT')
        yesterday = timezone.now() - timedelta(days=1)
        Commission.objects.create(affiliate=affiliate, kind='stake', ticket='S1', base_amount=D('100'), rate=D('30'),
                                  amount=D('30'), status='approved', decided_at=yesterday)
        self.close(['1000', '0', '0', '0'])
        res = self.api(self.boss).post(URL + 'expenses/', {'day': self.today.isoformat(), 'category': 'ai',
                                                           'amount': '45.50', 'note': 'Claude, November'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        pool = res.json()['pool']
        self.assertEqual((pool['earned'], pool['affiliate_costs'], pool['expenses'], pool['remaining']),
                         ('700.00', '30.00', '45.50', '624.50'))
        self.assertEqual(pool['expenses_by_category'], {'ai': '45.50'})
        self.assertEqual(self.api(self.boss).delete(URL + f'expenses/{res.json()["id"]}/').status_code, 204)
        self.assertEqual(services.pool_summary()['remaining'], '670.00')

    def test_expense_rules(self):
        for body in ({'day': self.today.isoformat(), 'category': 'ai', 'amount': '0'},
                     {'day': self.today.isoformat(), 'category': 'yachts', 'amount': '5'},
                     {'day': (self.today + timedelta(days=2)).isoformat(), 'category': 'ai', 'amount': '5'},
                     {'day': 'soon', 'category': 'ai', 'amount': '5'}):
            self.assertEqual(self.api(self.boss).post(URL + 'expenses/', body, format='json').status_code, 400, body)


class AccessTests(Base):
    def test_who_sees_what(self):
        stranger = User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True)
        self.assertEqual(self.api(stranger).get(URL).status_code, 403)
        self.assertEqual(APIClient().get(URL).status_code, 401)
        mine = self.api(self.partners[0]).get(URL).json()
        self.assertEqual((mine['role'], mine['wallet']['slot']), ('holder', 1))
        self.assertNotIn('wallets', mine)                                   # never the others' wallets
        boss = self.api(self.boss).get(URL).json()
        self.assertEqual((boss['role'], len(boss['wallets'])), ('superuser', 3))

    def test_only_a_superuser_runs_it(self):
        holder = self.api(self.partners[0])
        self.assertEqual(holder.post(URL + 'withdrawals/1/decide/', {'decision': 'paid'}, format='json').status_code, 403)
        self.assertEqual(holder.post(URL + 'expenses/', {}, format='json').status_code, 403)
        self.assertEqual(holder.put(URL + 'settings/', {'share_percent': '30'}, format='json').status_code, 403)

    def test_settings_rules(self):
        boss = self.api(self.boss)
        player_login = User.objects.create_user('punter', 'pu@example.com', 'x')
        self.assertEqual(boss.put(URL + 'settings/', {'wallets': [{'slot': 1, 'holder_id': player_login.id}]}, format='json').status_code, 400)
        self.assertEqual(boss.put(URL + 'settings/', {'wallets': [{'slot': 2, 'holder_id': self.partners[0].id}]}, format='json').status_code, 400)
        self.assertEqual(boss.put(URL + 'settings/', {'share_percent': '34'}, format='json').status_code, 400)
        self.assertEqual(boss.put(URL + 'settings/', {'share_percent': '12.5'}, format='json').json()['settings']['share_percent'], '12.50')
        self.close(['1', '1', '1', '1'])
        res = boss.put(URL + 'settings/', {'started_on': (self.today - timedelta(days=30)).isoformat()}, format='json')
        self.assertEqual(res.status_code, 400)                              # locked once days are shared
        self.assertTrue(AuditLog.objects.filter(event_type='revenue_settings').exists())
