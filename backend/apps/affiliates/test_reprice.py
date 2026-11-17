"""Repricing deposit commissions (CPA) to 10% of the first deposit: terms for
every agent, and commissions already paid above it cut, with the excess taken
back the way the audit does (balance, then Winnings, then future commissions)."""
from decimal import Decimal as D
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from apps.accounts import services as accounts
from apps.affiliates import reprice, services
from apps.affiliates.models import Affiliate, AffiliateProgramme, Commission, CommissionReversal
from apps.wallet import services as wallet


class RepriceTests(TestCase):
    def setUp(self):
        self.agent_player = accounts.create_player(username='agent')
        self.agent = services.apply(player_id=self.agent_player.id, code='AGENT')
        services.set_status(self.agent.id, Affiliate.Status.ACTIVE)
        Affiliate.objects.filter(pk=self.agent.pk).update(cpa_percent=D('30'), cpa_amount=D('0'), cpa_cap=D('100'))
        self.agent.refresh_from_db()

    def cpa(self, first='1', amount='0.30', status=Commission.Status.APPROVED, note=''):
        p = accounts.create_player(username=f'c{Commission.objects.count()}')
        ref = services.attach_referral(player_id=p.id, code='AGENT')
        return Commission.objects.create(affiliate=self.agent, kind=Commission.Kind.CPA, referral=ref,
                                         base_amount=D(first), rate=D('30'), amount=D(amount), status=status, note=note)

    def test_dry_run_changes_nothing(self):
        c = self.cpa()
        out = StringIO()
        call_command('reprice_cpa', stdout=out)
        self.assertIn('paid 0.30 -> 0.10', out.getvalue())
        c.refresh_from_db()
        self.agent.refresh_from_db()
        self.assertEqual((c.amount, self.agent.cpa_percent), (D('0.30'), D('30.00')))

    def test_apply_sets_terms_and_cuts_paid_commissions_to_ten_percent(self):
        paid = self.cpa(first='1', amount='0.30')                           # 30% of 1.00
        flat = self.cpa(first='2', amount='5.50', note='CPA restored 2026-11-16: 0 -> 5.50')   # old flat terms
        fair = self.cpa(first='5', amount='0.50')                           # already 10%
        pending = self.cpa(first='3', amount='0.90', status=Commission.Status.PENDING)
        Affiliate.objects.filter(pk=self.agent.pk).update(cpa_amount=D('4.90'))
        out = StringIO()
        call_command('reprice_cpa', '--apply', '--by', 'ops', stdout=out)
        for c in (paid, flat, fair, pending):
            c.refresh_from_db()
        self.assertEqual([c.amount for c in (paid, flat, fair, pending)], [D('0.10'), D('0.20'), D('0.50'), D('0.30')])
        self.assertEqual((paid.rate, paid.status), (D('10.00'), Commission.Status.APPROVED))
        self.assertTrue(paid.note.startswith('CPA repriced'))
        self.agent.refresh_from_db()
        self.assertEqual((self.agent.cpa_percent, self.agent.cpa_amount), (D('10.00'), D('0.00')))
        self.assertEqual(AffiliateProgramme.load().default_cpa_percent, D('10.00'))
        # The pool gets back what was taken from approved commissions (not the pending one).
        self.assertEqual(sum(r.amount for r in CommissionReversal.objects.all()), D('0.20') + D('5.30'))
        # Idempotent.
        self.assertEqual(reprice.run(apply=True), [])

    def test_excess_comes_from_the_wallet_when_the_balance_was_paid_out(self):
        c = self.cpa(first='1', amount='0.30', status=Commission.Status.PAID)
        wallet.credit(player_id=self.agent_player.id, amount=D('0.30'), kind='affiliate', idempotency_key='aff1')
        reprice.run(apply=True)
        c.refresh_from_db()
        self.assertEqual(c.amount, D('0.10'))
        self.assertEqual(wallet.get_balances(self.agent_player.id)['winnings'], D('0.10'))

    def test_future_commissions_use_ten_percent(self):
        reprice.set_terms(D('10'))
        self.agent.refresh_from_db()
        self.assertEqual(services.utils.deposit_commission(D('1'), self.agent.cpa_amount, self.agent.cpa_percent,
                                                           self.agent.cpa_cap), D('0.10'))


class NetLossRateMigrationTests(TestCase):
    """Migration 0017: every agent's net-loss commission is 20% from now on;
    commissions already earned are untouched."""

    def test_moves_every_agent_to_twenty_and_keeps_earned_commissions(self):
        import importlib
        from django.apps import apps as dj_apps
        mig = importlib.import_module('apps.affiliates.migrations.0017_net_loss_twenty_percent')
        p = accounts.create_player(username='agent2')
        a = services.apply(player_id=p.id, code='AG2')
        Affiliate.objects.filter(pk=a.pk).update(revshare_percent=D('30'))
        earned = Commission.objects.create(affiliate=a, kind=Commission.Kind.NET_LOSS, base_amount=D('19.23'),
                                           rate=D('30'), amount=D('5.76'), status=Commission.Status.APPROVED)
        mig.every_agent_twenty_percent(dj_apps, None)
        a.refresh_from_db()
        earned.refresh_from_db()
        self.assertEqual(a.revshare_percent, D('20.00'))
        self.assertEqual(AffiliateProgramme.load().default_revshare_percent, D('20.00'))
        self.assertEqual((earned.rate, earned.amount), (D('30.00'), D('5.76')))
