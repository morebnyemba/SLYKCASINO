"""Clawing back deposit commissions (CPA) the old rules over-paid: a referral
deposits 1.00, plays bonus money, and the agent got a 5.20 CPA."""
from decimal import Decimal as D
from io import StringIO
from itertools import count

from django.core.management import call_command
from django.test import TestCase

from apps.accounts import services as accounts
from apps.affiliates import clawback, services
from apps.affiliates.models import Affiliate, Commission, Payout
from apps.wallet import services as wallet

_k = count()


class _Agent(TestCase):
    def setUp(self):
        services.update_programme(welcome_bonus_percent=0, cpa_min_turnover_multiple=3)
        self.agent_player = accounts.create_player(username='agent')
        self.agent = services.apply(player_id=self.agent_player.id, code='AGENT')
        services.set_status(self.agent.id, Affiliate.Status.ACTIVE)
        # 4.90 flat + 30% of the first deposit, minimum deposit 1: 1.00 -> 5.20.
        Affiliate.objects.filter(pk=self.agent.pk).update(cpa_amount=D('4.90'), cpa_percent=D('30'), cpa_cap=D('100'),
                                                          cpa_min_deposit=D('1'))
        self.agent.refresh_from_db()

    def customer(self, name, deposit='1', real_bet='1', bonus_bet='2', topup=None):
        p = accounts.create_player(username=name)
        services.attach_referral(player_id=p.id, code='AGENT')
        wallet.deposit(player_id=p.id, amount=D(deposit), idempotency_key=f'd{next(_k)}')
        if topup:
            wallet.deposit(player_id=p.id, amount=D(topup), idempotency_key=f'd{next(_k)}')
        wallet.credit(player_id=p.id, amount=D('2.50'), kind='bonus', idempotency_key=f'bo{next(_k)}')
        if D(real_bet):
            wallet.debit(player_id=p.id, amount=D(real_bet), kind='bet_stake', bucket='deposit', idempotency_key=f'b{next(_k)}')
        if D(bonus_bet):
            wallet.debit(player_id=p.id, amount=D(bonus_bet), kind='bet_stake', bucket='bonus', idempotency_key=f'b{next(_k)}')
        return p

    def old_cpa(self, player, amount='5.20', status=Commission.Status.APPROVED, note='First deposit 1.00: 30% + 4.90 flat'):
        """What the old rules created (bonus stakes counted, 1x play-through)."""
        return Commission.objects.create(affiliate=self.agent, kind=Commission.Kind.CPA,
                                         referral=self.agent.referrals.get(player_id=player.id),
                                         base_amount=D('1'), rate=D('30'), amount=D(amount), status=status, note=note)

    def paid_to_wallet(self, amount):
        payout = Payout.objects.create(affiliate=self.agent, amount=D(amount), method=Payout.Method.WALLET)
        services.complete_wallet_payout(payout.id, notify=False)

    def winnings(self):
        return wallet.get_balances(self.agent_player.id)['winnings']

    def balance(self):
        return services.balance(Affiliate.objects.get(pk=self.agent.pk))



class ClawbackTests(_Agent):
    def test_live_rules_no_longer_pay_it(self):
        self.customer('cust')
        self.assertEqual(services.compute_cpa(Affiliate.objects.get(pk=self.agent.pk)), 0)

    def test_dry_run_changes_nothing(self):
        c = self.old_cpa(self.customer('cust'))
        self.paid_to_wallet('5.20')
        out = StringIO()
        call_command('reverse_cpa_overpayments', stdout=out)
        self.assertIn('excess 5.20', out.getvalue())
        self.assertIn('DRY RUN', out.getvalue())
        c.refresh_from_db()
        self.assertEqual((c.amount, c.status), (D('5.20'), Commission.Status.APPROVED))
        self.assertEqual(self.winnings(), D('5.20'))

    def test_paid_into_the_wallet_comes_back_from_the_wallet(self):
        c = self.old_cpa(self.customer('cust'))
        self.paid_to_wallet('5.20')
        [res] = clawback.run(apply=True, by='ops')
        self.assertEqual((res.reversed, res.from_balance, res.from_wallet, res.carried),
                         (D('5.20'), D('0.00'), D('5.20'), D('0.00')))
        c.refresh_from_db()
        self.assertEqual((c.amount, c.status), (D('0.00'), Commission.Status.REJECTED))
        self.assertIn('CPA clawback', c.note)
        self.assertEqual(self.winnings(), D('0.00'))
        b = self.balance()
        self.assertEqual((b['available'], b['paid_out']), (D('0.00'), D('0.00')))
        self.assertEqual(clawback.run(apply=True), [])                                  # idempotent
        self.assertEqual(self.winnings(), D('0.00'))

    def test_spent_money_is_netted_off_future_commissions(self):
        self.old_cpa(self.customer('cust'))
        self.paid_to_wallet('5.20')
        wallet.debit(player_id=self.agent_player.id, amount=D('3.20'), kind='bet_stake', bucket='winnings',
                     idempotency_key='spent')
        [res] = clawback.run(apply=True)
        self.assertEqual((res.from_wallet, res.carried), (D('2.00'), D('3.20')))
        self.assertEqual(self.winnings(), D('0.00'))
        self.assertEqual(self.balance()['available'], D('0.00'))
        Commission.objects.create(affiliate=self.agent, kind=Commission.Kind.STAKE, ticket='S1', amount=D('4.00'),
                                  status=Commission.Status.APPROVED)
        self.assertEqual(self.balance()['available'], D('0.80'))                    # 4.00 - 3.20 still owed

    def test_unpaid_balance_absorbs_it_without_touching_the_wallet(self):
        wallet.credit(player_id=self.agent_player.id, amount=D('10'), kind='adjustment', bucket='winnings',
                      idempotency_key='own')
        self.old_cpa(self.customer('cust'))
        Commission.objects.create(affiliate=self.agent, kind=Commission.Kind.STAKE, ticket='S1', amount=D('1.00'),
                                  status=Commission.Status.APPROVED)
        [res] = clawback.run(apply=True)
        self.assertEqual((res.from_balance, res.from_wallet), (D('5.20'), D('0.00')))
        self.assertEqual(self.winnings(), D('10.00'))
        self.assertEqual(self.balance()['available'], D('1.00'))

    def test_legacy_paid_commission(self):
        self.old_cpa(self.customer('cust'), status=Commission.Status.PAID)
        wallet.credit(player_id=self.agent_player.id, amount=D('5.20'), kind='affiliate', idempotency_key='legacy')
        [res] = clawback.run(apply=True)
        self.assertEqual((res.from_wallet, res.carried), (D('5.20'), D('0.00')))
        b = self.balance()
        self.assertEqual((b['available'], b['paid_out'], self.winnings()), (D('0.00'), D('0.00'), D('0.00')))

    def test_pending_is_rejected_and_qualified_is_kept(self):
        pending = self.old_cpa(self.customer('pend'), status=Commission.Status.PENDING)
        good = self.old_cpa(self.customer('good', real_bet='3', bonus_bet='0', topup='2'))  # played 3x in real money
        [res] = clawback.run(apply=True)
        self.assertEqual([r.commission_id for r in res.rows], [pending.id])
        pending.refresh_from_db(); good.refresh_from_db()
        self.assertEqual(pending.status, Commission.Status.REJECTED)
        self.assertEqual((good.status, good.amount), (Commission.Status.APPROVED, D('5.20')))

    def test_staff_waived_commissions_are_reported_not_reversed(self):
        c = self.old_cpa(self.customer('cust'), note='First deposit 1.00: 30% — paid by ops (rules waived)')
        [res] = clawback.run(apply=True)
        self.assertTrue(res.rows[0].waived)
        c.refresh_from_db()
        self.assertEqual(c.amount, D('5.20'))
        clawback.run(apply=True, include_waived=True)
        c.refresh_from_db()
        self.assertEqual(c.status, Commission.Status.REJECTED)

    def test_deleted_customer_is_listed_and_skipped_unless_asked(self):
        p = self.customer('gone')
        c = self.old_cpa(p)
        self.paid_to_wallet('5.20')
        services.erase_player_data(p.id)                                           # referral -> NULL
        out = StringIO()
        call_command('reverse_cpa_overpayments', '--apply', stdout=out)            # must not crash
        self.assertIn('deleted customer', out.getvalue())
        self.assertIn('[customer deleted — skipped]', out.getvalue())
        c.refresh_from_db()
        self.assertEqual(c.amount, D('5.20'))
        call_command('reverse_cpa_overpayments', '--apply', '--include-deleted', stdout=StringIO())
        c.refresh_from_db()
        self.assertEqual(c.status, Commission.Status.REJECTED)
        self.assertEqual(self.winnings(), D('0.00'))
        n = clawback.notice(Affiliate.objects.get(pk=self.agent.pk))                # notice copes with it too
        self.assertEqual(n['items'][0]['reversed'], '5.20')


class AuditNoticeTests(_Agent):
    """What the agent dashboard says after the audit."""

    def notice(self, **kw):
        return clawback.notice(Affiliate.objects.get(pk=self.agent.pk), **kw)

    def test_nothing_before_any_audit(self):
        self.assertIsNone(self.notice())

    def test_unaffected_agent_is_told_it_passed_for_30_days(self):
        clawback.run(apply=True)
        n = self.notice()
        self.assertFalse(n['affected'])
        self.assertEqual((n['turnover_multiple'], n['items']), ('3.00', []))
        from datetime import timedelta
        from django.utils import timezone
        self.assertIsNone(self.notice(now=timezone.now() + timedelta(days=31)))

    def test_affected_agent_sees_what_and_how(self):
        self.old_cpa(self.customer('customer1'))
        self.paid_to_wallet('5.20')
        wallet.debit(player_id=self.agent_player.id, amount=D('3.20'), kind='bet_stake', bucket='winnings',
                     idempotency_key='spent')
        clawback.run(apply=True, by='ops')
        n = self.notice()
        self.assertTrue(n['affected'])
        self.assertEqual((n['reversed_total'], n['from_wallet'], n['still_owed'], n['from_balance']),
                         ('5.20', '2.00', '3.20', '0.00'))
        [item] = n['items']
        self.assertEqual((item['paid'], item['kept'], item['reversed']), ('5.20', '0.00', '5.20'))
        self.assertIn('bonus money doesn’t count', item['reason'])
        self.assertNotEqual(item['customer'], 'customer1')                       # masked
        from datetime import timedelta
        from django.utils import timezone
        self.assertIsNotNone(self.notice(now=timezone.now() + timedelta(days=60)))
        self.assertIsNone(self.notice(now=timezone.now() + timedelta(days=91)))

    def test_affected_agent_is_notified(self):
        from apps.notifications.models import Notification
        self.old_cpa(self.customer('cust'))
        clawback.run(apply=True)
        self.assertTrue(Notification.objects.filter(player_id=self.agent_player.id, title__startswith='Commission audit').exists())
