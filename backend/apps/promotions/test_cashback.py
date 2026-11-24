from datetime import date, timedelta
from decimal import Decimal as D
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from apps.promotions import cashback, refunds
from apps.promotions.models import CashbackPayout, CashbackSettings, CashbackTier, LossRefundSettings
from apps.sportsbook import services as sb
from apps.sportsbook.models import BetSlip, Event
from apps.wallet import services as wallet


def winnings(pid):
    return wallet.get_balances(pid)['winnings']


class LostByOneRefundTests(TestCase):
    def setUp(self):
        self.p = accounts.register_player(username='punter', email='p@example.com', password='Pass-word-123')
        wallet.credit(player_id=self.p.id, amount=D('100'), kind='deposit', idempotency_key='dep')
        soon = timezone.now() + timedelta(days=1)
        self.events = [Event.objects.create(name=f'Home{i} vs Away{i}', starts_at=soon, status='NS', is_open=True,
                                            odds=D(o), odds_draw=D('3.0'), odds_away=D('3.0')) for i, o in enumerate(('5.00', '5.00', '2.00'))]

    def place(self, stake='1', wallet_id='deposit'):
        legs = [{'event': e.name, 'odds': str(e.odds), 'event_id': e.id, 'selection': 'home'} for e in self.events]
        return sb.place_accumulator(wallet=wallet_id, stake=D(stake), player_id=self.p.id, legs=legs)  # 5 × 5 × 2 = 50

    def settle(self, outcomes):
        for e, r in zip(self.events, outcomes):
            sb.settle_event(e.id, r)

    def test_lost_on_one_match_pays_stake_x_odds_over_25_over_lost_odds(self):
        slip = self.place(stake='2')
        before = winnings(self.p.id)
        self.settle(['home', 'home', 'away'])                       # lost on the 2.00
        self.assertEqual(BetSlip.objects.get(pk=slip.pk).status, 'lost')
        self.assertEqual(winnings(self.p.id) - before, D('2.00'))   # 2 × 50 ÷ 25 ÷ 2.00
        sb._settle_slip_if_ready(slip.pk)                           # once only
        self.assertEqual(winnings(self.p.id) - before, D('2.00'))

    def test_waits_for_the_other_matches_after_an_early_loss(self):
        slip = self.place()
        before = winnings(self.p.id)
        sb.settle_event(self.events[0].id, 'away')                  # lost at once on the first leg
        self.assertEqual(BetSlip.objects.get(pk=slip.pk).status, 'lost')
        self.assertEqual(winnings(self.p.id), before)               # two matches still to play
        sb.settle_event(self.events[1].id, 'home')
        sb.settle_event(self.events[2].id, 'home')
        self.assertEqual(winnings(self.p.id) - before, D('0.40'))   # 1 × 50 ÷ 25 ÷ 5.00

    def test_no_refund_for_two_losses_low_odds_bonus_or_switched_off(self):
        self.place()
        before = winnings(self.p.id)
        self.settle(['away', 'away', 'home'])                       # lost on two matches
        self.assertEqual(winnings(self.p.id), before)
        cfg = LossRefundSettings.load()
        cfg.min_odds = D('60')
        cfg.save()
        slip = self.place()
        self.assertIsNone(refunds.amount_for(BetSlip.objects.get(pk=slip.pk)))

    def test_cap(self):
        cfg = LossRefundSettings.load()
        cfg.max_refund = D('1.50')
        cfg.save()
        self.place(stake='2')
        before = winnings(self.p.id)
        self.settle(['home', 'home', 'away'])
        self.assertEqual(winnings(self.p.id) - before, D('1.50'))


class CashbackTests(TestCase):
    def setUp(self):
        self.p = accounts.register_player(username='loser', email='l@example.com', password='Pass-word-123')
        self.q = accounts.register_player(username='small', email='s@example.com', password='Pass-word-123')
        for pl in (self.p, self.q):
            wallet.credit(player_id=pl.id, amount=D('500'), kind='deposit', idempotency_key=f'dep:{pl.id}')
        cfg = CashbackSettings.load()
        cfg.enabled, cfg.period_days, cfg.starts_on = True, 7, timezone.localdate() - timedelta(days=7)
        cfg.save()
        CashbackTier.objects.create(name='Silver', min_loss=D('50'), percent=D('5'), min_tickets=2, min_active_days=1)
        CashbackTier.objects.create(name='Gold', min_loss=D('200'), percent=D('10'), max_amount=D('25'), min_tickets=3, min_active_days=1)

    def lose(self, pl, amount, n, days_ago=3):
        when = timezone.now() - timedelta(days=days_ago)
        for i in range(n):
            with patch('django.utils.timezone.now', return_value=when):
                wallet.debit(player_id=pl.id, amount=D(amount), kind='bet_stake', bucket='deposit',
                             idempotency_key=f'st:{pl.id}:{i}:{amount}', reference='t')
                BetSlip.objects.create(player_id=pl.id, stake=D(amount), combined_odds=D('3'), status='lost', wallet='deposit')

    def test_best_tier_pays_once_to_winnings(self):
        self.lose(self.p, '100', 3)                                   # lost 300 on 3 tickets: Gold 10% = 30, capped at 25
        self.lose(self.q, '20', 2)                                    # lost 40: below every tier
        reports = cashback.run()
        self.assertEqual((reports[0]['paid'], reports[0]['total']), (1, D('25.00')))
        self.assertEqual(wallet.get_balances(self.p.id)['winnings'], D('25.00'))
        self.assertEqual(cashback.run(), [])                          # the period is done
        self.assertEqual(CashbackPayout.objects.count(), 1)
        self.assertEqual(wallet.get_balances(self.q.id)['winnings'], D('0.00'))

    def test_ticket_and_day_rules(self):
        self.lose(self.p, '100', 1)                                   # 100 lost but only 1 ticket: no tier
        self.assertEqual(cashback.run()[0]['paid'], 0)

    def test_switched_off_and_unfinished_periods_pay_nothing(self):
        cfg = CashbackSettings.load()
        cfg.starts_on = timezone.localdate() - timedelta(days=3)
        cfg.save()
        self.lose(self.p, '100', 3, days_ago=1)
        self.assertEqual(cashback.run(), [])                          # the period hasn't ended
        cfg.enabled = False
        cfg.starts_on = timezone.localdate() - timedelta(days=7)
        cfg.save()
        self.assertEqual(cashback.run(), [])

    def test_admin_rules_superuser_only(self):
        clerk, boss = APIClient(), APIClient()
        clerk.force_authenticate(User.objects.create_user('clerk', 'c@example.com', 'x', is_staff=True))
        boss.force_authenticate(User.objects.create_superuser('boss', 'b@example.com', 'x'))
        self.assertEqual(clerk.get('/api/admin/cashback/').status_code, 200)
        self.assertEqual(clerk.put('/api/admin/cashback/', {'refund': {'enabled': False}}, format='json').status_code, 403)
        out = boss.put('/api/admin/cashback/', {'refund': {'enabled': True, 'min_odds': '30', 'divisor': '25', 'max_refund': ''},
                                                'tiers': [{'name': 'Only', 'min_loss': '10', 'percent': '7', 'min_tickets': 0,
                                                           'min_active_days': 0}]}, format='json').json()
        self.assertEqual((out['refund']['min_odds'], [t['name'] for t in out['tiers']]), ('30.00', ['Only']))
        bad = boss.put('/api/admin/cashback/', {'tiers': [{'min_loss': '10', 'percent': '150'}]}, format='json')
        self.assertEqual(bad.status_code, 400)
