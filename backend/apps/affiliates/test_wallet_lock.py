"""Agent earnings stay in the agent wallet, locked for the month they were
earned in; from the 1st of the next month the agent moves them to Winnings or
withdraws them."""
from datetime import date, timedelta
from decimal import Decimal as D

import pytest
from django.test import TestCase
from django.utils import timezone

from apps.accounts import services as accounts
from apps.affiliates import services
from apps.affiliates.models import Affiliate, AffiliateProgramme, Commission
from apps.wallet import services as wallet_services

pytestmark = pytest.mark.affiliate_lock


class WalletLockTests(TestCase):
    def setUp(self):
        AffiliateProgramme.load()
        AffiliateProgramme.objects.update(auto_payout=False, min_payout=D('1'))
        self.player = accounts.create_player(username='agent')
        self.agent = services.apply(player_id=self.player.id, code='AGENT')
        services.set_status(self.agent.id, Affiliate.Status.ACTIVE)
        self.today = timezone.localdate()
        self.last_month = self.today.replace(day=1) - timedelta(days=3)

    def earn(self, amount, day, kind='netloss'):
        return Commission.objects.create(affiliate=self.agent, kind=kind, period=day, base_amount=D(amount) * 4, rate=D('25'),
                                         amount=D(amount), status='approved', decided_at=timezone.now())

    def test_this_months_earnings_are_locked_until_the_1st(self):
        self.earn('40', self.last_month)
        self.earn('15', self.today)
        b = services.balance(Affiliate.objects.get(pk=self.agent.pk))
        self.assertEqual((b['available'], b['locked']), (D('40.00'), D('15.00')))
        first = self.today.replace(day=1)
        self.assertEqual(b['unlocks_on'], date(first.year + (first.month == 12), first.month % 12 + 1, 1))
        with self.assertRaisesMessage(services.AffiliateError, 'unlocks on'):
            services.request_payout(affiliate_id=self.agent.id, amount='50', method='wallet')

    def test_agent_chooses_to_move_unlocked_money_to_winnings(self):
        self.earn('40', self.last_month)
        services.request_payout(affiliate_id=self.agent.id, amount='40', method='wallet')
        self.assertEqual(wallet_services.get_balances(self.player.id)['winnings'], D('40.00'))
        self.assertEqual(services.balance(Affiliate.objects.get(pk=self.agent.pk))['available'], D('0.00'))

    def test_next_month_everything_earned_before_unlocks(self):
        self.earn('15', self.today)
        nxt = (self.today.replace(day=28) + timedelta(days=5)).replace(day=1)
        b = services.balance(Affiliate.objects.get(pk=self.agent.pk), today=nxt)
        self.assertEqual((b['available'], b['locked'], b['unlocks_on']), (D('15.00'), D('0.00'), None))

    def test_money_already_moved_earlier_counts_against_this_month_not_last(self):
        """Before the lock, auto payout moved this month's money already; the lock
        never shows a negative or double balance."""
        self.earn('30', self.today)
        from apps.affiliates.models import Payout
        Payout.objects.create(affiliate=self.agent, amount=D('20'), method='wallet', status='paid')
        b = services.balance(Affiliate.objects.get(pk=self.agent.pk))
        self.assertEqual((b['available'], b['locked']), (D('0.00'), D('10.00')))

    def test_auto_payout_off_keeps_earnings_out_of_winnings(self):
        self.earn('40', self.last_month)
        services.pay_out_earnings()
        self.assertEqual(wallet_services.get_balances(self.player.id)['winnings'], D('0.00'))

    def test_switching_the_lock_off_frees_everything(self):
        self.earn('15', self.today)
        services.update_programme(lock_until_month_end=False)
        self.assertEqual(services.balance(Affiliate.objects.get(pk=self.agent.pk))['available'], D('15.00'))

