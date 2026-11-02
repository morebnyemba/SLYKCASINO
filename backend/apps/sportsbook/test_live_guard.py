"""The in-play guard: the lock minute, automatic holds, and staff control."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts.models import AuditLog
from apps.risk.models import RiskSignal
from apps.sportsbook import services as sb
from apps.sportsbook.clients import LiveOddsSnapshot
from apps.sportsbook.market_feed import parse_live_odds
from apps.sportsbook.models import Bet, LiveTradingSettings
from apps.sportsbook.test_in_play import FEED_ODDS, LIVE, InPlayBase
from apps.wallet import services as wallet_services

D = Decimal


def snap(*, elapsed=30, goals=(0, 0), home='1.50', status='Second Half'):
    one_x_two, markets = parse_live_odds(FEED_ODDS, first_half=False)
    return LiveOddsSnapshot(external_id='555', status=status, elapsed=elapsed, goals_home=goals[0], goals_away=goals[1],
                            blocked=False, one_x_two=(D(home), one_x_two[1], one_x_two[2]), markets=tuple(markets))


@LIVE
class GuardTests(InPlayBase):
    def setUp(self):
        super().setUp()
        LiveTradingSettings.objects.update_or_create(pk=1, defaults={
            'lock_minute': 60, 'price_jump_percent': 50, 'burst_amount': D('500'), 'burst_minutes': 5})
        self.now = timezone.now()

    def apply(self, seconds=0, **kw):
        sb.apply_live_odds(snap(**kw), now=self.now + timedelta(seconds=seconds))
        self.event.refresh_from_db()
        return self.event

    def test_locks_at_the_minute_and_stays_locked(self):
        self.assertTrue(sb.in_play_bettable(self.apply(elapsed=59)))
        ev = self.apply(5, elapsed=60)
        self.assertIsNotNone(ev.live_locked_at)
        self.assertFalse(sb.in_play_bettable(ev, now=self.now + timedelta(seconds=6)))
        self.assertEqual(sb.trading_state(ev)['live_closed'], 'In-play betting closes at 60\'')
        # A feed that later reports an earlier minute doesn't reopen it.
        ev = self.apply(10, elapsed=59)
        self.assertIsNotNone(ev.live_locked_at)
        self.assertFalse(sb.in_play_bettable(ev, now=self.now + timedelta(seconds=11)))

    def test_lock_rejects_a_bet_still_in_its_acceptance_delay(self):
        self.apply(elapsed=59)
        bet = sb.place_bet(wallet='deposit', event='A', stake=D('10'), odds=D('1.50'), player_id=self.player.id,
                           event_id=self.event.id, selection='home')
        self.assertEqual(bet.status, Bet.Status.ACCEPTING)
        later = bet.placed_at + timedelta(seconds=8)
        sb.apply_live_odds(snap(elapsed=60), now=later)
        self.assertEqual(sb.confirm_live_bet('bet', bet.id, now=later), 'rejected')
        self.assertEqual(wallet_services.get_balance(self.player.id), D('100'))

    def test_the_fixtures_poll_also_locks(self):
        from apps.sportsbook.clients import FixtureUpdate
        self.event.elapsed = 58
        self.event.save(update_fields=['elapsed'])
        sb.sync_fixture(FixtureUpdate(external_id='555', name='Arsenal vs Chelsea', status='2H', elapsed=61,
                                      goals_home=0, goals_away=0, starts_at=None))
        self.event.refresh_from_db()
        self.assertIsNotNone(self.event.live_locked_at)

    def test_price_jump_without_a_goal_holds_but_a_goal_explains_it(self):
        self.apply(home='1.50')
        ev = self.apply(5, home='3.50')                               # +133% with no goal
        self.assertIn('jumped', ev.live_hold_reason)
        self.assertFalse(sb.in_play_bettable(ev, now=self.now + timedelta(seconds=6)))
        self.assertEqual(sb.trading_state(ev)['live_closed'], 'In-play betting is suspended')
        # Another match: the same move right after a goal is fine.
        self.event.live_hold_reason, self.event.live_hold_at = '', None
        self.event.save(update_fields=['live_hold_reason', 'live_hold_at'])
        self.apply(20, home='3.50')
        ev = self.apply(25, home='1.20', goals=(1, 0))
        self.assertEqual(ev.live_hold_reason, '')

    def test_score_going_down_or_clock_going_back_holds(self):
        self.apply(goals=(1, 0))
        ev = self.apply(5, goals=(0, 0))
        self.assertIn('Score went from 1-0 to 0-0', ev.live_hold_reason)
        self.event.live_hold_reason = ''
        self.event.save(update_fields=['live_hold_reason'])
        self.apply(10, elapsed=40)
        ev = self.apply(15, elapsed=30)
        self.assertIn('clock went back', ev.live_hold_reason)

    def test_burst_of_money_on_one_pick_holds_and_flags_the_bettors(self):
        self.apply()
        wallet_services.credit(player_id=self.player.id, amount=D('1000'), kind='deposit', idempotency_key='more')
        for _ in range(2):
            sb.place_bet(wallet='deposit', event='A', stake=D('300'), odds=D('1.50'), player_id=self.player.id,
                         event_id=self.event.id, selection='home')
        self.event.refresh_from_db()
        self.assertIn('staked in play on one selection', self.event.live_hold_reason)
        self.assertTrue(RiskSignal.objects.filter(player_id=self.player.id, code='live_bet_before_suspension').exists())
        self.assertTrue(AuditLog.objects.filter(event_type='live_market_held').exists())


@LIVE
class StaffControlTests(InPlayBase):
    def setUp(self):
        super().setUp()
        self.staff = APIClient()
        self.staff.force_authenticate(User.objects.create_user('trader', 't@example.com', 'x', is_staff=True))
        sb.apply_live_odds(snap(), now=timezone.now())

    def test_staff_suspend_and_reopen_but_cannot_undo_the_lock(self):
        url = f'/api/admin/sportsbook/events/{self.event.id}/'
        self.assertEqual(self.staff.post(url + 'live-hold/', {'reason': ''}, format='json').status_code, 400)
        res = self.staff.post(url + 'live-hold/', {'reason': 'Red card not in the feed yet'}, format='json')
        self.assertIn('Suspended by trader', res.json()['live_hold_reason'])
        self.event.refresh_from_db()
        self.assertFalse(sb.in_play_bettable(self.event))
        res = self.staff.post(url + 'live-release/', format='json')
        self.assertEqual(res.json()['live_hold_reason'], '')
        self.assertEqual(self.staff.post(url + 'live-release/', format='json').status_code, 409)
        # Past the lock minute, reopening a hold doesn't reopen betting.
        sb.apply_live_odds(snap(elapsed=61), now=timezone.now())
        self.staff.post(url + 'live-hold/', {'reason': 'checking'}, format='json')
        self.staff.post(url + 'live-release/', format='json')
        self.event.refresh_from_db()
        self.assertFalse(sb.in_play_bettable(self.event))
        self.assertTrue(AuditLog.objects.filter(event_type='live_market_released').exists())

    def test_settings(self):
        url = '/api/admin/sportsbook/live-trading/'
        self.assertEqual(self.staff.put(url, {'lock_minute': 200}, format='json').status_code, 400)
        res = self.staff.put(url, {'lock_minute': 70, 'burst_amount': '250'}, format='json').json()
        self.assertEqual((res['lock_minute'], res['burst_amount']), (70, '250.00'))
        self.assertEqual(self.staff.get(url).json()['held'], [])
        self.assertEqual(APIClient().get(url).status_code, 401)
