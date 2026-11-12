"""Agents earn their % of what their customers actually lose (net, pooled,
closed daily) — and each way of gaming the old per-losing-ticket rule fails."""
from datetime import datetime, time, timedelta
from decimal import Decimal as D
from itertools import count
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from apps.affiliates import netloss, services
from apps.affiliates.models import Affiliate, AffiliateProgramme, Commission, NetLossDay
from apps.sportsbook.models import Bet
from apps.wallet import services as wallet

_keys = count()
TODAY = timezone.localdate()
D1, D2, D3 = (TODAY - timedelta(days=n) for n in (3, 2, 1))


def at(day, hour=12):
    return timezone.make_aware(datetime.combine(day, time(hour)))


class Base(TestCase):
    def setUp(self):
        services.update_programme(welcome_bonus_percent=0)
        AffiliateProgramme.objects.update(net_loss_since=at(D1, 0), net_loss_review_above=0)
        agent = accounts.create_player(username='agent')
        self.agent_player = agent
        self.agent = services.apply(player_id=agent.id, code='AGENT')
        services.set_status(self.agent.id, Affiliate.Status.ACTIVE)
        Affiliate.objects.filter(pk=self.agent.pk).update(active_since=at(D1, 0) - timedelta(days=5))
        self.c1 = self.customer('c1')
        self.c2 = self.customer('c2')

    def customer(self, name):
        p = accounts.create_player(username=name)
        services.attach_referral(player_id=p.id, code='AGENT')
        from apps.affiliates.models import Referral
        Referral.objects.filter(player_id=p.id).update(created_at=at(D1, 0) - timedelta(days=5))
        return p

    def fund(self, player, amount='1000'):
        with patch('django.utils.timezone.now', return_value=at(D1, 0) - timedelta(days=1)):
            wallet.deposit(player_id=player.id, amount=D(amount), idempotency_key=f'dep{next(_keys)}')

    def play(self, player, day, stake, won='0', hour=12, bucket='deposit', kind=('bet_stake', 'bet_payout')):
        with patch('django.utils.timezone.now', return_value=at(day, hour)):
            wallet.debit(player_id=player.id, amount=D(stake), kind=kind[0], bucket=bucket, idempotency_key=f'k{next(_keys)}')
            if D(won) > 0:
                wallet.credit(player_id=player.id, amount=D(won), kind=kind[1], bucket=bucket if bucket == 'bonus' else 'winnings',
                              idempotency_key=f'k{next(_keys)}')

    def close(self, today=TODAY):
        return netloss.close_days(today=today)

    def day(self, d):
        return NetLossDay.objects.get(affiliate=self.agent, day=d)

    def paid(self):
        return sum((c.amount for c in Commission.objects.filter(affiliate=self.agent, kind='netloss')), D('0'))


class NetLossTests(Base):
    def test_pays_on_net_loss_not_on_losing_stakes(self):
        self.fund(self.c1)
        self.play(self.c1, D1, '100')                    # lost
        self.play(self.c1, D1, '100', won='140')          # won
        self.assertEqual(self.close(), 3)                 # D1, D2, D3 closed, in order
        d = self.day(D1)
        self.assertEqual((d.stakes, d.wins, d.net_loss), (D('200.00'), D('140.00'), D('60.00')))
        self.assertEqual(d.commission.amount, D('18.00'))  # 30% of 60 — the old rule paid 30% of 100 = 30
        self.assertEqual(d.commission.status, Commission.Status.APPROVED)
        self.assertEqual(self.close(), 0)                 # idempotent
        self.assertEqual(self.paid(), D('18.00'))

    def test_a_winning_day_is_carried_forward(self):
        self.fund(self.c1)
        self.play(self.c1, D1, '50', won='100')           # customer +50
        self.play(self.c1, D2, '80')                      # customer −80
        self.close()
        self.assertEqual((self.day(D1).carry_out, self.day(D1).commission), (D('-50.00'), None))
        self.assertEqual(self.day(D2).commission.amount, D('9.00'))   # (80 − 50) × 30%
        self.assertEqual(self.day(D2).carry_out, D('0'))

    def test_hedging_both_sides_with_two_customers_pays_only_the_house_margin(self):
        self.fund(self.c1); self.fund(self.c2)
        self.play(self.c1, D1, '100', won='190')          # home wins
        self.play(self.c2, D1, '100')                     # away loses
        self.close()
        self.assertEqual(self.day(D1).commission.amount, D('3.00'))   # 30% of 10; the pair is down 7

    def test_agent_own_account_winnings_count_against_the_pool_and_its_losses_earn_nothing(self):
        self.fund(self.c1); self.fund(self.agent_player)
        self.play(self.c1, D1, '100')                     # customer loses
        self.play(self.agent_player, D1, '100', won='190')  # agent hedges on their own account
        self.play(self.agent_player, D2, '50')            # agent's own loss: no rebate
        self.close()
        self.assertEqual(self.day(D1).hedge, D('-90.00'))
        self.assertEqual(self.day(D1).commission.amount, D('3.00'))
        self.assertIsNone(self.day(D2).commission)

    def test_accounts_sharing_a_payment_number_are_treated_as_the_agents(self):
        from apps.wallet.models import PaymentTransaction
        outsider = accounts.create_player(username='cousin')
        for i, pid in enumerate((self.agent_player.id, outsider.id)):
            PaymentTransaction.objects.create(reference=f'pt{i}', player_id=pid, method='ecocash', phone='0771234567',
                                              amount=D('10'), status=PaymentTransaction.Status.PAID)
        self.fund(self.c1); self.fund(outsider)
        self.play(self.c1, D1, '100')
        self.play(outsider, D1, '100', won='190')
        self.close()
        self.assertEqual((self.day(D1).hedge, self.day(D1).commission.amount), (D('-90.00'), D('3.00')))

    def test_a_stake_counts_only_once_its_bet_has_settled(self):
        """Open bets at midnight can't be cashed in: an agent stacking late bets
        that win the next day earns nothing."""
        self.fund(self.c1)
        self.play(self.c1, D1, '100', hour=23)
        bet = Bet.objects.create(wallet='deposit', player_id=self.c1.id, stake=D('100'), odds=D('1.9'), event='x',
                                 status='won', payout=D('190'))
        Bet.objects.filter(pk=bet.pk).update(placed_at=at(D1, 23), settled_at=at(D2, 15))
        with patch('django.utils.timezone.now', return_value=at(D2, 15)):
            wallet.credit(player_id=self.c1.id, amount=D('190'), kind='bet_payout', bucket='winnings', idempotency_key='win')
        self.close()
        self.assertEqual((self.day(D1).open_out, self.day(D1).net_loss, self.day(D1).commission), (D('100.00'), D('0'), None))
        self.assertEqual((self.day(D2).open_in, self.day(D2).net_loss), (D('100.00'), D('-90.00')))
        self.assertEqual(self.paid(), D('0'))

    def test_aviator_and_casino_count_bonus_play_never_does(self):
        self.fund(self.c1)
        self.play(self.c1, D1, '40', won='10', kind=('casino_debit', 'casino_credit'))    # Aviator: net 30
        with patch('django.utils.timezone.now', return_value=at(D1, 1)):
            wallet.credit(player_id=self.c1.id, amount=D('500'), kind='bonus', bucket='bonus', idempotency_key='b')
        self.play(self.c1, D1, '200', bucket='bonus')                                     # lost bonus: not money
        self.close()
        self.assertEqual((self.day(D1).net_loss, self.day(D1).commission.amount), (D('30.00'), D('9.00')))

    def test_bonus_turned_into_winnings_is_a_cost(self):
        self.fund(self.c1)
        self.play(self.c1, D1, '100')
        with patch('django.utils.timezone.now', return_value=at(D1, 14)):
            wallet.credit(player_id=self.c1.id, amount=D('40'), kind='bonus_conversion', bucket='winnings', idempotency_key='cv')
        self.close()
        self.assertEqual(self.day(D1).net_loss, D('60.00'))

    def test_nothing_before_the_switch_or_before_the_customer_was_linked(self):
        late = accounts.create_player(username='late')
        self.fund(self.c1); self.fund(late)
        services.link_customer(self.agent.id, late.id, credit_from=at(D2, 0))
        self.play(late, D1, '100')                        # before they were linked
        self.play(late, D2, '10')
        with patch('django.utils.timezone.now', return_value=at(D1, 0) - timedelta(hours=1)):
            wallet.debit(player_id=self.c1.id, amount=D('500'), kind='bet_stake', bucket='deposit', idempotency_key='old')  # before the switch
        self.close()
        self.assertEqual(self.day(D1).net_loss, D('0'))
        self.assertEqual(self.day(D2).commission.amount, D('3.00'))

    def test_big_days_wait_for_review(self):
        AffiliateProgramme.objects.update(net_loss_review_above=D('20'))
        self.fund(self.c1)
        self.play(self.c1, D1, '100')
        self.close()
        c = self.day(D1).commission
        self.assertEqual((c.amount, c.status), (D('30.00'), Commission.Status.PENDING))
        self.assertEqual(services.balance(Affiliate.objects.get(pk=self.agent.pk))['available'], D('0'))
        services.approve(c.id)
        self.assertEqual(services.balance(Affiliate.objects.get(pk=self.agent.pk))['available'], D('30.00'))

    def test_suspended_agents_are_not_closed_and_resume_without_back_pay(self):
        self.fund(self.c1)
        services.set_status(self.agent.id, Affiliate.Status.SUSPENDED)
        self.play(self.c1, D1, '100')
        self.assertEqual(self.close(), 0)
        with patch('django.utils.timezone.now', return_value=at(D2, 0)):
            services.set_status(self.agent.id, Affiliate.Status.ACTIVE)
        self.play(self.c1, D2, '10')
        self.close()
        self.assertEqual(self.paid(), D('3.00'))

    def test_dashboard_estimates_today(self):
        self.fund(self.c1)
        with patch('django.utils.timezone.now', return_value=timezone.now() - timedelta(minutes=5)):
            wallet.debit(player_id=self.c1.id, amount=D('50'), kind='bet_stake', bucket='deposit', idempotency_key='now')
        stats = services.dashboard(Affiliate.objects.get(pk=self.agent.pk))
        self.assertEqual((stats['net_loss_today'], stats['commission_today']), (D('50.00'), D('15.00')))

    def test_per_ticket_crediting_stops_at_the_switch(self):
        self.fund(self.c1)
        Bet.objects.create(wallet='deposit', player_id=self.c1.id, stake=D('100'), odds=D('2'), event='x',
                           status='lost', settled_at=timezone.now() - timedelta(minutes=10))
        self.assertEqual(services.credit_losing_tickets(), 0)
        self.assertEqual(services.catch_up_losing_tickets(), 0)


class AdminTests(Base):
    def test_statements_and_close_now(self):
        self.fund(self.c1)
        self.play(self.c1, D1, '100', won='40')
        api = APIClient()
        api.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x' * 12, is_staff=True))
        self.assertEqual(api.get('/api/admin/affiliates/crediting-health/').json()['days_behind'], {'agents': 1, 'days': 3})
        self.assertEqual(api.post('/api/admin/affiliates/credit-missed/').json()['days'], 3)
        body = api.get(f'/api/admin/affiliates/{self.agent.id}/statements/').json()
        first = body['days'][-1]
        self.assertEqual((first['day'], first['net_loss'], first['commission'], first['status']),
                         (D1.isoformat(), '60.00', '18.00', 'approved'))
        self.assertEqual(api.get('/api/admin/affiliates/crediting-health/').json()['days_behind'], {'agents': 0, 'days': 0})
        res = api.put('/api/admin/affiliate-programme/', {'net_loss_review_above': '75'}, format='json')
        self.assertEqual(res.json()['net_loss_review_above'], '75.00')
