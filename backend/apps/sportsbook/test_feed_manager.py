"""The feed manager: counts api-football requests, keeps a reserve for settling
bets, and paces each scheduled fetch so the daily quota lasts until it resets."""
from datetime import datetime, timedelta, timezone as dt_timezone
from unittest.mock import MagicMock, patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.sportsbook import feed_manager as fm
from apps.sportsbook import services
from apps.sportsbook.clients import ApiFootballClient, FixtureLeague, FixtureUpdate
from apps.sportsbook.models import Event, FeedJob, FeedQuotaDay, LeagueSetting


def resp(remaining=None, limit=None, payload=None):
    r = MagicMock()
    r.headers = {k: v for k, v in (('x-ratelimit-requests-remaining', remaining),
                                   ('x-ratelimit-requests-limit', limit)) if v is not None}
    r.json.return_value = payload or {'response': []}
    r.raise_for_status.return_value = None
    return r


@override_settings(API_FOOTBALL_KEY='k', API_FOOTBALL_DAILY_LIMIT=1000, API_FOOTBALL_RESERVE_PERCENT=5)
class FeedManagerTests(TestCase):
    def set_left(self, left, limit=1000):
        row, _ = FeedQuotaDay.objects.get_or_create(provider=fm.PROVIDER, day=fm.provider_day())
        FeedQuotaDay.objects.filter(pk=row.pk).update(remaining=left, limit=limit)

    def test_counts_requests_and_stores_what_the_provider_reports(self):
        fm.after_request(resp(remaining='812', limit='1000'), kind='odds')
        fm.after_request(resp(), kind='odds')                         # no headers: count down ourselves
        row = FeedQuotaDay.objects.get(day=fm.provider_day())
        self.assertEqual((row.used, row.remaining, row.limit), (2, 811, 1000))
        self.assertEqual(FeedJob.objects.get(kind='odds').requests_today, 2)

    def test_reserve_is_kept_for_critical_fetches(self):
        self.set_left(40)                                             # reserve is 5% of 1000 = 50
        with self.assertRaises(fm.QuotaHold):
            fm.before_request('live_odds')
        fm.before_request('settle')                                   # settling bets may still call
        fm.before_request('manual')
        self.set_left(0)
        with self.assertRaises(fm.QuotaHold):
            fm.before_request('settle')

    def test_a_held_request_never_reaches_the_provider(self):
        self.set_left(10)
        with patch('apps.sportsbook.clients.requests.get') as get:
            with fm.job('import', force=True):
                self.assertEqual(ApiFootballClient().fetch_fixtures(date='2026-11-17'), [])
        get.assert_not_called()

    def test_quiet_day_uses_the_base_interval_and_a_busy_day_stretches_it(self):
        self.set_left(200000, limit=200000)                           # plenty: every base interval
        self.assertEqual(fm.interval('live_odds'), 10)
        self.assertEqual(fm.interval('odds'), 3600)
        self.set_left(1000)                                           # 950 spendable over the rest of the day
        stretched = fm.interval('live_odds')
        self.assertGreater(stretched, 10)
        self.assertEqual(fm.interval('odds'), 3600)                   # a cheap hourly job still gets all it needs
        alloc = fm.allocation()
        self.assertAlmostEqual(sum(alloc.values()), 950, delta=1)     # never plans past what's left
        self.assertGreater(alloc['live_odds'], alloc['import'])       # the hungry polls get the leftovers
        self.set_left(50)                                             # only the reserve left
        self.assertIsNone(fm.interval('live_odds'))
        self.assertEqual(fm.interval('settle'), 180)                  # critical: never paced

    def test_live_scores_relax_while_live_odds_are_flowing(self):
        self.set_left(200000, limit=200000)
        self.assertEqual(fm.interval('live_scores'), 20)
        from decimal import Decimal
        Event.objects.create(name='A v B', odds=Decimal('2'), starts_at=timezone.now(), live_odds_at=timezone.now())
        self.assertEqual(fm.interval('live_scores'), 60)

    def test_a_job_runs_when_due_counts_its_cost_and_skips_otherwise(self):
        self.set_left(1000)
        with fm.job('odds') as go:
            self.assertTrue(go)
            for _ in range(4):
                fm.after_request(resp())
        j = FeedJob.objects.get(kind='odds')
        self.assertEqual((j.runs_today, j.requests_today, round(j.cost, 2)), (1, 4, 1.9))   # 0.7*1 + 0.3*4
        with fm.job('odds') as go:
            self.assertFalse(go)                                      # hourly: not due again yet
        self.assertEqual(FeedJob.objects.get(kind='odds').skipped_today, 1)
        with fm.job('odds', force=True) as go:
            self.assertTrue(go)                                       # an operator's "run now"

    def test_the_day_resets_at_utc_midnight(self):
        late = datetime(2026, 11, 17, 23, 59, 30, tzinfo=dt_timezone.utc)
        self.assertEqual(fm.provider_day(late).isoformat(), '2026-11-17')
        self.assertEqual(fm.seconds_left_today(late), 60.0)           # never below a minute

    def test_status_for_the_console(self):
        fm.after_request(resp(remaining='900', limit='1000'), kind='settle')
        s = fm.status()
        self.assertEqual((s['limit'], s['remaining'], s['reserve'], s['used_by_us']), (1000, 900, 50, 1))
        self.assertIn('live_odds', {j['kind'] for j in s['jobs']})


@override_settings(API_FOOTBALL_KEY='k')
class DateImportTests(TestCase):
    def fixture(self, ext, league_id):
        return FixtureUpdate(
            external_id=ext, name=f'Team{ext} v Other', status='NS', starts_at=timezone.now() + timedelta(days=1),
            goals_home=None, goals_away=None,
            league=FixtureLeague(external_id=league_id, name=f'League {league_id}', country='X'),
        )

    def test_one_request_per_day_covers_every_league_and_skips_disabled_ones(self):
        LeagueSetting.objects.create(provider='api-football', league_id=2, name='Off', enabled=False)
        calls = []

        def fake(self, *, date=None, **kw):
            calls.append(date)
            return [self.outer.fixture(f'{date}-1', 1), self.outer.fixture(f'{date}-2', 2)]

        ApiFootballClient.outer = self
        try:
            with patch.object(ApiFootballClient, 'fetch_fixtures', fake):
                fetched = services.import_upcoming_by_date(days=2)
        finally:
            del ApiFootballClient.outer
        self.assertEqual(len(calls), 3)                               # today + 2 days: 3 requests in all
        self.assertEqual(fetched, 6)
        self.assertEqual(Event.objects.count(), 3)                    # league 2 is disabled
        self.assertTrue(LeagueSetting.objects.filter(league_id=1, enabled=True).exists())


@override_settings(SPORTSBOOK_LIVE_ODDS_STALE=60)
class LiveStaleWindowTests(TestCase):
    def test_follows_the_live_odds_interval_but_never_below_the_setting(self):
        fm._planned_memo.update(at=0.0)
        self.assertEqual(fm.live_odds_stale_seconds(), 60)
        FeedJob.objects.update_or_create(kind='live_odds', defaults={'planned_interval': 40.0})
        fm._planned_memo.update(at=0.0)
        self.assertEqual(fm.live_odds_stale_seconds(), 100)          # 2.5 polls at 40s
        FeedJob.objects.filter(kind='live_odds').update(planned_interval=10.0)
        fm._planned_memo.update(at=0.0)
        self.assertEqual(fm.live_odds_stale_seconds(), 60)
