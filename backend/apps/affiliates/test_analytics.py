"""Affiliate and platform analytics: KPIs per timeframe, chart series,
campaigns, activity and the API endpoints."""
from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APIClient

from apps.accounts import services as account_services
from apps.affiliates import services
from apps.wallet import services as wallet_services
from common import timeframes

from .tests import Base

D = Decimal


class TimeframeTests(SimpleTestCase):
    def test_every_frame_resolves(self):
        for frame in timeframes.FRAMES:
            if frame == 'custom':
                continue
            w = timeframes.resolve(frame)
            self.assertIn(w.bucket, timeframes.BUCKETS)
            self.assertTrue(w.start is None or w.start < w.end)
        self.assertIsNone(timeframes.resolve('all').start)
        self.assertEqual(timeframes.resolve('live').bucket, 'minute')
        self.assertEqual(timeframes.resolve('today').bucket, 'hour')
        self.assertEqual(timeframes.resolve('30d').bucket, 'day')
        self.assertEqual(timeframes.resolve('this_year').bucket in ('day', 'month'), True)

    def test_custom_and_bad_input(self):
        w = timeframes.resolve('custom', start='2026-01-01', end='2026-01-31')
        self.assertEqual(w.bucket, 'day')
        self.assertEqual(len(timeframes.bucket_starts(w)), 31)
        with self.assertRaises(timeframes.TimeframeError):
            timeframes.resolve('custom', start='2026-01-01')
        with self.assertRaises(timeframes.TimeframeError):
            timeframes.resolve('fortnight')


class AffiliateAnalyticsTests(Base):
    def setUp(self):
        super().setUp()
        self.affiliate = self.make_affiliate(revshare_percent='25')
        for campaign in ('fb', 'fb', 'tw', ''):
            services.record_click(self.affiliate.code, campaign=campaign)
        self.a = self.referred('alice_ref', self.affiliate)
        self.b = self.referred('bob_ref', self.affiliate)
        self.play(self.a, staked='30', won='10', deposit='50')
        wallet_services.credit(player_id=self.b.id, amount=D('20'), kind='deposit', idempotency_key='b-dep')
        wallet_services.debit(player_id=self.b.id, amount=D('5'), kind='casino_debit', idempotency_key='b-jet')
        # Someone who wasn't referred never shows up.
        outsider = account_services.create_player(username='outsider')
        self.play(outsider, staked='500', won='0', deposit='900')

    def test_kpis_for_today(self):
        k = services.affiliate_analytics(self.affiliate, 'today')['kpis']
        self.assertEqual((k['clicks'], k['signups'], k['ftds'], k['referrals_total']), (4, 2, 2, 2))
        self.assertEqual(k['signup_rate'], '50.0')
        self.assertEqual(k['ftd_rate'], '100.0')
        self.assertEqual(k['deposits'], '70.00')
        self.assertEqual(k['plays'], 2)
        self.assertEqual(k['stakes'], '35.00')
        self.assertEqual(k['wins'], '10.00')
        self.assertEqual(k['player_losses'], '25.00')
        self.assertEqual(k['ngr'], '25.00')
        self.assertEqual(k['revshare_estimate'], '6.25')
        self.assertEqual(k['sportsbook']['stakes'], '30.00')
        self.assertEqual(k['casino'], {'plays': 1, 'stakes': '5.00', 'wins': '0.00', 'ggr': '5.00'})
        self.assertEqual(k['active_players'], 2)

    def test_other_windows(self):
        y = services.affiliate_analytics(self.affiliate, 'yesterday')['kpis']
        self.assertEqual((y['clicks'], y['signups'], y['plays'], y['deposits']), (0, 0, 0, '0.00'))
        for frame in ('live', '7d', '30d', 'this_month', 'this_year', 'all'):
            self.assertEqual(services.affiliate_analytics(self.affiliate, frame)['kpis']['deposits'], '70.00', frame)

    def test_series_campaigns_players_and_activity(self):
        data = services.affiliate_analytics(self.affiliate, 'today')
        self.assertEqual(sum(D(p['stakes']) for p in data['series']), D('35.00'))
        self.assertEqual(sum(p['clicks'] for p in data['series']), 4)
        self.assertEqual(sum(p['ftds'] for p in data['series']), 2)
        fb = next(c for c in data['campaigns'] if c['campaign'] == 'fb')
        self.assertEqual(fb['clicks'], 2)
        self.assertEqual(len(data['players']), 2)
        self.assertTrue(all('*' in p['player'] for p in data['players']))  # masked
        kinds = {a['kind'] for a in data['activity']}
        self.assertTrue({'deposit', 'bet_stake', 'signup'} <= kinds)

    def _client(self, player):
        user = get_user_model().objects.create_user(username=player.username, password='pw')
        player.user = user
        player.save(update_fields=['user'])
        api = APIClient()
        api.force_authenticate(user)
        return api

    def test_endpoints(self):
        api = self._client(self.partner)
        res = api.get('/api/affiliates/me/analytics/', {'frame': '7d'})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()['kpis']['deposits'], '70.00')
        self.assertEqual(api.get('/api/affiliates/me/analytics/', {'frame': 'nope'}).status_code, 400)
        self.assertEqual(api.get('/api/admin/analytics/').status_code, 403)

        self.assertEqual(self._client(self.a).get('/api/affiliates/me/analytics/').status_code, 404)

        staff = get_user_model().objects.create_user('staff', 'staff@example.com', 'x', is_staff=True)
        api = APIClient()
        api.force_authenticate(staff)
        res = api.get(f'/api/admin/affiliates/{self.affiliate.id}/analytics/', {'frame': 'all'})
        self.assertEqual(res.status_code, 200)
        platform = api.get('/api/admin/analytics/', {'frame': 'today'}).json()
        self.assertEqual(platform['kpis']['deposits'], '970.00')
        self.assertEqual(platform['kpis']['affiliate']['deposits'], '70.00')
        self.assertEqual(platform['top_affiliates'][0]['code'], self.affiliate.code)
        self.assertIn('right_now', platform)
        custom = api.get('/api/admin/analytics/', {'frame': 'custom', 'start': '2026-01-01', 'end': '2026-01-07'})
        self.assertEqual(custom.status_code, 200)
        self.assertEqual(len(custom.json()['series']), 7)
