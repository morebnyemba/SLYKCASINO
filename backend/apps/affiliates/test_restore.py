"""Restoring audited CPA commissions that met the rules in force when paid
(1x the first deposit in real money), on 30%-of-first-deposit terms."""
from datetime import timedelta
from decimal import Decimal as D
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.utils import timezone

from apps.affiliates import clawback, restore, services
from apps.affiliates.models import Affiliate, Commission, CommissionReversal
from apps.affiliates.test_clawback import _Agent
from apps.wallet import services as wallet


class RestoreTests(_Agent):
    def setUp(self):
        super().setUp()
        Affiliate.objects.filter(pk=self.agent.pk).update(cpa_amount=0, cpa_percent=D('30'), cpa_cap=0)
        self.agent.refresh_from_db()

    def thirty(self, name, real_bet, bonus_bet='0'):
        """A 1.00 first deposit and the 0.30 CPA the old rules paid."""
        return self.old_cpa(self.customer(name, real_bet=real_bet, bonus_bet=bonus_bet), amount='0.30',
                            note='First deposit 1.00: 30%')

    def test_genuine_is_restored_bonus_only_stays(self):
        good = self.thirty('good', real_bet='1')                 # 1x real: met the old rule
        bad = self.thirty('bad', real_bet='0', bonus_bet='2')    # only bonus money
        clawback.run(apply=True)
        self.assertEqual(self.balance()['available'], D('0.00'))
        out = StringIO()
        call_command('restore_cpa', stdout=out)                   # dry run
        self.assertIn('To restore: 1 commission(s), 0.15', out.getvalue())
        good.refresh_from_db()
        self.assertEqual(good.status, Commission.Status.REJECTED)
        [res] = restore.run(apply=True, by='ops')
        self.assertEqual((res.restored, res.to_wallet), (D('0.15'), D('0.00')))
        good.refresh_from_db(); bad.refresh_from_db()
        self.assertEqual((good.status, good.amount), (Commission.Status.APPROVED, D('0.15')))     # 15% of 1.00
        self.assertTrue(good.note.startswith('CPA restored'))
        self.assertEqual(good.decided_at, good.created_at)
        self.assertEqual(bad.status, Commission.Status.REJECTED)
        self.assertEqual(self.balance()['available'], D('0.15'))
        n = clawback.notice(Affiliate.objects.get(pk=self.agent.pk))
        self.assertEqual((n['restored_total'], n['restored_count'], n['restored_percent']), ('0.15', 1, '15'))
        self.assertEqual(n['reversed_total'], '0.45')                          # bad 0.30 + the other half of good
        self.assertIn('Restored at 15%', [i['reason'] for i in n['items']][0].replace('Met the rules in force when you were paid; r', 'R'))
        [again] = restore.run(apply=True)                          # idempotent: only the kept one is left
        self.assertEqual((again.restored, [r.restore for r in again.rows]), (D('0.00'), [False]))
        self.assertEqual(self.balance()['available'], D('0.15'))

    def test_wallet_money_goes_back_to_the_wallet(self):
        self.thirty('good', real_bet='1')
        self.paid_to_wallet('0.30')
        clawback.run(apply=True)
        self.assertEqual(self.winnings(), D('0.00'))
        [res] = restore.run(apply=True)
        self.assertEqual(res.to_wallet, D('0.15'))
        self.assertEqual(self.winnings(), D('0.15'))
        b = self.balance()
        self.assertEqual((b['available'], b['paid_out']), (D('0.00'), D('0.15')))

    def test_flat_terms_get_only_the_percentage_part(self):
        Affiliate.objects.filter(pk=self.agent.pk).update(cpa_amount=D('5'), cpa_percent=D('20'), cpa_cap=D('5'))
        self.agent.refresh_from_db()
        c = self.old_cpa(self.customer('cust', real_bet='1', bonus_bet='0'))          # 5.20 on 1.00, bet 1x real
        self.old_cpa(self.customer('bonus', real_bet='0', bonus_bet='2'))             # only bonus money
        clawback.run(apply=True)
        [res] = restore.run(apply=True)
        self.assertEqual(res.restored, D('0.15'))                                    # 15% (below the agent's 20%)
        c.refresh_from_db()
        self.assertEqual((c.status, c.amount), (Commission.Status.APPROVED, D('0.15')))
        self.assertEqual(self.balance()['available'], D('0.15'))
        n = clawback.notice(Affiliate.objects.get(pk=self.agent.pk))
        self.assertEqual((n['restored_total'], n['reversed_total']), ('0.15', '10.25'))   # 5.05 + 5.20
        self.assertIn('flat CPA stays reversed', n['items'][0]['reason'])

    def test_pool_is_charged_again(self):
        from apps.revenue import services as revenue
        from apps.revenue.models import RevenueSettings
        today = timezone.localdate()
        cfg = RevenueSettings.load(); cfg.started_on = today - timedelta(days=3); cfg.save()

        def close(day):
            with patch.object(revenue, 'day_ggr', return_value=D('0')):
                revenue.close_days(today=day)
        c = self.thirty('good', real_bet='1')
        when = timezone.now() - timedelta(days=2)
        Commission.objects.filter(pk=c.pk).update(created_at=when, decided_at=when)
        close(today)
        self.assertEqual(revenue.pool_summary()['affiliate_costs'], '0.30')
        clawback.run(apply=True)
        restore.run(apply=True)
        self.assertEqual(sorted(CommissionReversal.objects.values_list('amount', flat=True)), [D('-0.15'), D('0.30')])
        close(today + timedelta(days=1))
        self.assertEqual(revenue.pool_summary()['affiliate_costs'], '0.15')   # charged only what was restored
