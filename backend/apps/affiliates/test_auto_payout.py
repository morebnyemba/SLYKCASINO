"""Affiliate earnings are paid into the affiliate's Winnings wallet — withdrawable
like any winnings — the moment they are final, with no payout request."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal as D

import pytest
from django.contrib.auth.models import User
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as account_services
from apps.affiliates import services
from apps.affiliates.models import Affiliate, AffiliateProgramme, Commission, Payout
from apps.notifications.models import Notification
from apps.sportsbook.models import Bet
from apps.wallet import services as wallet_services

pytestmark = pytest.mark.affiliate_auto


class AutoPayoutBase(TestCase):
    def setUp(self):
        services.update_programme(welcome_bonus_percent=0, default_cpa_percent=30, default_cpa_cap=100,
                                  cpa_min_turnover_multiple=1)
        self.partner = account_services.create_player(username='partner')
        self.affiliate = services.apply(player_id=self.partner.id, code='PARTNER')
        services.set_status(self.affiliate.id, Affiliate.Status.ACTIVE)
        self.affiliate.refresh_from_db()
        self.customer = account_services.create_player(username='customer')
        services.attach_referral(player_id=self.customer.id, code='PARTNER')

    def winnings(self):
        return wallet_services.get_balances(self.partner.id)['winnings']

    def available(self):
        return services.balance(Affiliate.objects.get(pk=self.affiliate.pk))['available']

    def lose_ticket(self, stake='100', minutes_ago=5):
        bet = Bet.objects.create(wallet='deposit', player_id=self.customer.id, stake=D(stake), odds=D('2'), event='x', status='lost')
        Bet.objects.filter(pk=bet.pk).update(settled_at=timezone.now() - timedelta(minutes=minutes_ago))
        return bet


class AutoPayoutTests(AutoPayoutBase):
    def test_on_by_default(self):
        AffiliateProgramme.objects.all().delete()
        programme = AffiliateProgramme.load()
        self.assertTrue(programme.auto_payout and programme.auto_approve_commissions)

    def test_losing_ticket_share_lands_in_winnings_once_final(self):
        self.lose_ticket('100', minutes_ago=1)                      # still inside the correction window
        self.assertEqual(services.credit_losing_tickets(), 0)
        self.assertEqual(self.winnings(), D('0.00'))
        self.lose_ticket('100', minutes_ago=5)
        self.assertEqual(services.credit_losing_tickets(), 1)
        self.assertEqual(self.winnings(), D('30.00'))              # 30% of the stake, withdrawable
        self.assertEqual(self.available(), D('0.00'))              # nothing left waiting in the affiliate balance
        payout = Payout.objects.get()
        self.assertEqual((payout.method, payout.status, payout.note), ('wallet', 'paid', services.AUTO_PAYOUT_NOTE))

    def test_never_pays_twice(self):
        self.lose_ticket('100')
        services.credit_losing_tickets()
        services.credit_losing_tickets()
        services.pay_out_earnings()
        services.pay_out_earnings(affiliate_id=self.affiliate.id)
        self.assertEqual(self.winnings(), D('30.00'))
        self.assertEqual(Payout.objects.count(), 1)

    def test_deposit_commission_is_paid_as_soon_as_it_qualifies(self):
        wallet_services.deposit(player_id=self.customer.id, amount=D('50'), idempotency_key='d1')
        wallet_services.debit(player_id=self.customer.id, amount=D('50'), kind='bet_stake', bucket='deposit', idempotency_key='s1')
        self.assertEqual(services.compute_cpa(self.affiliate), 1)
        commission = Commission.objects.get(kind='cpa')
        self.assertEqual(commission.status, Commission.Status.APPROVED)       # no operator approval needed
        self.assertEqual(self.winnings(), D('15.00'))
        self.assertTrue(Notification.objects.filter(player_id=self.partner.id, title='Affiliate commission paid').exists())

    def test_with_approval_required_it_waits_then_pays_on_approval(self):
        services.update_programme(auto_approve_commissions=False)
        wallet_services.deposit(player_id=self.customer.id, amount=D('50'), idempotency_key='d1')
        wallet_services.debit(player_id=self.customer.id, amount=D('50'), kind='bet_stake', bucket='deposit', idempotency_key='s1')
        services.compute_cpa(self.affiliate)
        commission = Commission.objects.get(kind='cpa')
        self.assertEqual((commission.status, self.winnings()), (Commission.Status.PENDING, D('0.00')))
        services.pay_out_earnings()
        self.assertEqual(self.winnings(), D('0.00'))                # pending is not final
        services.approve(commission.id)
        self.assertEqual(self.winnings(), D('15.00'))

    def test_a_suspended_affiliate_is_not_paid_until_reactivated(self):
        services.set_status(self.affiliate.id, Affiliate.Status.SUSPENDED)
        self.lose_ticket('100')
        Commission.objects.create(affiliate=self.affiliate, kind=Commission.Kind.STAKE, ticket='S999', base_amount=D('100'),
                                  rate=D('30'), amount=D('30'), status=Commission.Status.APPROVED, decided_at=timezone.now())
        services.pay_out_earnings()
        self.assertEqual(self.winnings(), D('0.00'))
        services.set_status(self.affiliate.id, Affiliate.Status.ACTIVE)
        services.pay_out_earnings()
        self.assertEqual(self.winnings(), D('30.00'))

    def test_earnings_from_before_it_was_switched_on_are_swept_in(self):
        services.update_programme(auto_payout=False)
        self.lose_ticket('100')
        services.credit_losing_tickets()
        self.assertEqual((self.available(), self.winnings()), (D('30.00'), D('0.00')))   # manual mode: stays in balance
        services.update_programme(auto_payout=True)
        self.assertEqual(services.pay_out_earnings(), {'affiliates': 1, 'amount': '30.00'})
        self.assertEqual((self.available(), self.winnings()), (D('0.00'), D('30.00')))

    def test_money_already_requested_to_mobile_money_is_left_alone_and_a_declined_one_is_paid(self):
        services.update_programme(auto_payout=False, min_payout=1)
        self.lose_ticket('100')
        services.credit_losing_tickets()
        from apps.accounts.models import Player
        Player.objects.filter(pk=self.partner.id).update(kyc_status='verified')
        payout = services.request_payout(affiliate_id=self.affiliate.id, amount='20', method='ecocash', account_number='0771234567')
        services.update_programme(auto_payout=True)
        services.pay_out_earnings()
        self.assertEqual(self.winnings(), D('10.00'))               # only what wasn't requested
        services.reject_payout(payout.id, note='Wrong number')
        services.pay_out_earnings()
        self.assertEqual(self.winnings(), D('30.00'))

    def test_the_wallet_money_can_be_withdrawn_like_winnings(self):
        self.lose_ticket('100')
        services.credit_losing_tickets()
        self.assertEqual(wallet_services.get_balance_dto(self.partner.id).winnings, D('30.00'))

    def test_admin_switches_both_settings(self):
        staff = APIClient()
        staff.force_authenticate(User.objects.create_superuser('ops', 'o@example.com', 'x'))
        body = staff.get('/api/admin/affiliate-programme/').json()
        self.assertTrue(body['auto_payout'] and body['auto_approve_commissions'])
        body = staff.put('/api/admin/affiliate-programme/', {'auto_payout': False, 'auto_approve_commissions': False,
                                                              'external_payouts': False}, format='json').json()
        self.assertEqual((body['auto_payout'], body['auto_approve_commissions'], body['external_payouts']), (False, False, False))
