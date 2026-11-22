"""The Savings account: the part of the 30% partner pool no wallet holds."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.revenue import services, shares
from apps.revenue.models import RevenueDay, RevenueSettings, ShareWallet

D = Decimal
URL = '/api/admin/revenue-share/savings/'


@override_settings(REVENUE_SHARE_CONTROLLER_IDS=[])      # ids 1/2 are controllers by default
class SavingsTests(TestCase):
    def setUp(self):
        self.boss = User.objects.create_superuser('boss', 'b@example.com', 'x')
        self.p2 = User.objects.create_user('p2', 'p2@example.com', 'x', is_staff=True)
        self.p3 = User.objects.create_user('p3', 'p3@example.com', 'x', is_staff=True)
        self.clerk = User.objects.create_user('clerk', 'c@example.com', 'x', is_staff=True)
        cfg = RevenueSettings.load()
        cfg.started_on = timezone.localdate() - timedelta(days=2)
        cfg.save()
        services.update_settings(wallets=[{'slot': 1, 'holder_id': self.boss.id}, {'slot': 2, 'holder_id': self.p2.id},
                                          {'slot': 3, 'holder_id': self.p3.id}], by='setup')
        for slot in (1, 2, 3):                                    # 3 owners at 3% each = 9% held, 21% unheld
            ShareWallet.objects.filter(slot=slot).update(percent=D('3'))

    def close(self, ggr='1000'):
        with patch.object(services, 'day_ggr', return_value=D(ggr)):
            services.close_days()

    def test_three_percent_each_leaves_twenty_one_percent_in_savings(self):
        self.close()
        for day in RevenueDay.objects.all():
            self.assertEqual((day.shared, day.savings, day.pool), (D('90.00'), D('210.00'), D('700.00')))
        s = services.savings_summary()
        self.assertEqual((s['balance'], s['saved_total'], s['unheld_percent'], s['held_percent']), ('420.00', '420.00', '21.00', '9.00'))
        self.assertEqual(services.pool_summary()['earned'], '1400.00')        # the operating pool keeps its 70% only

    def test_fully_held_pool_saves_nothing_and_a_losing_day_saves_nothing(self):
        ShareWallet.objects.filter(slot__in=(1, 2, 3)).update(percent=D('10'))
        self.close('-500')
        self.assertEqual(services.savings_summary()['balance'], '0.00')

    def test_using_the_savings(self):
        self.close()
        api = APIClient()
        api.force_authenticate(self.boss)
        body = api.post(URL, {'amount': '120', 'note': 'New server'}, format='json').json()
        self.assertEqual((body['balance'], body['used_total'], body['uses'][0]['note']), ('300.00', '120.00', 'New server'))
        res = api.post(URL, {'amount': '1000', 'note': 'Too much'}, format='json')
        self.assertIn('hold only $300.00', res.json()['detail'])
        self.assertEqual(api.post(URL, {'amount': '10', 'note': ''}, format='json').status_code, 400)
        clerk = APIClient()
        clerk.force_authenticate(self.clerk)
        self.assertEqual(clerk.get(URL).status_code, 403)                   # not a shareholder
        p2 = APIClient()
        p2.force_authenticate(self.p2)
        self.assertEqual(p2.get(URL).json()['balance'], '300.00')            # shareholders see it
        self.assertEqual(p2.post(URL, {'amount': '1', 'note': 'x'}, format='json').status_code, 400)

    def test_selling_a_share_shrinks_what_is_saved(self):
        shares.set_share(slot=1, percent='13', by_user=self.boss)            # raise to 13%: 19% held, 11% unheld
        self.close()
        day = RevenueDay.objects.order_by('-day').first()
        self.assertEqual((day.shared, day.savings, day.pool), (D('190.00'), D('110.00'), D('700.00')))
