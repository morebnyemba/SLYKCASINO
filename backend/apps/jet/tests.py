"""Jet: fairness maths, bets and cash-outs against the wallet, round
settlement, restart recovery, and the API surface."""
from __future__ import annotations

import random
from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as account_services
from apps.wallet import services as wallet_services

from . import engine, services
from .models import JetBet, JetRound, JetSettings

D = Decimal


class FairnessMathTests(SimpleTestCase):
    def test_crash_point_is_reproducible_and_verifiable(self):
        seed = 'a' * 64
        first = engine.crash_point(seed, 7, D('3'), D('1000'))
        self.assertEqual(first, engine.crash_point(seed, 7, D('3'), D('1000')))
        self.assertNotEqual(engine.seed_hash(seed), seed)
        self.assertGreaterEqual(first, D('1.00'))

    def test_house_edge_holds_for_any_target(self):
        # P(crash >= x) = (1 - edge) / x, so cashing out at x returns ~(1 - edge).
        rnd = random.Random(42)
        crashes = [engine.crash_point(f'{rnd.getrandbits(128):032x}', i, D('3'), D('1000')) for i in range(40000)]
        for target in (D('1.5'), D('2'), D('5')):
            rtp = sum(float(target) for c in crashes if c >= target) / len(crashes)
            self.assertAlmostEqual(rtp, 0.97, delta=0.03, msg=f'target {target}')

    def test_cap_and_flight_time(self):
        self.assertLessEqual(engine.crash_point('b' * 64, 1, D('0'), D('2')), D('2'))
        self.assertEqual(engine.multiplier_at(engine.seconds_to(D('2.00')) + 0.001), D('2.00'))
        self.assertEqual(engine.payout_for(D('10'), D('5000'), D('10000')), D('10000'))
        self.assertEqual(engine.mask_name('tendai'), 't***i')


def _player(name, funds='100'):
    player = account_services.create_player(username=name)
    user = User.objects.create(username=name)
    player.user = user
    player.save(update_fields=['user'])
    wallet_services.deposit(player_id=player.id, amount=D(funds), idempotency_key=f'seed:{name}')
    return player, user


def _balance(player):
    return wallet_services.get_balance_dto(player.id).balance


def _round(crash='2.00', now=None):
    """A round taking bets, with a known crash point."""
    rnd = services.open_round(now=now)
    JetRound.objects.filter(pk=rnd.pk).update(crash_point=D(crash))
    rnd.refresh_from_db()
    return rnd


class BettingTests(TestCase):
    def setUp(self):
        self.player, _ = _player('tendai')
        self.now = timezone.now()
        self.rnd = _round(now=self.now)

    def test_bet_debits_and_counts(self):
        bet = services.place_bet(player=self.player, stake='10', slot=1, auto_cashout='1.5', now=self.now)
        self.assertEqual((bet.status, bet.display_name, bet.auto_cashout), ('active', 't***i', D('1.50')))
        self.assertEqual(_balance(self.player), D('90.00'))
        self.rnd.refresh_from_db()
        self.assertEqual((self.rnd.total_stake, self.rnd.bet_count), (D('10.00'), 1))

    def test_bet_rules(self):
        cases = [
            dict(stake='0.01'), dict(stake='500'), dict(stake='5', slot=3), dict(stake='5', auto_cashout='1.00'),
        ]
        for kw in cases:
            with self.assertRaises(services.JetError, msg=kw):
                services.place_bet(player=self.player, now=self.now, **{'slot': 1, **kw})
        services.place_bet(player=self.player, stake='5', slot=1, now=self.now)
        with self.assertRaisesMessage(services.JetError, 'already have a bet'):
            services.place_bet(player=self.player, stake='5', slot=1, now=self.now)
        services.place_bet(player=self.player, stake='5', slot=2, now=self.now)  # second slot is fine
        with self.assertRaisesMessage(services.JetError, 'closed'):
            services.place_bet(player=self.player, stake='5', slot=1, now=self.rnd.betting_ends_at + timedelta(seconds=1))

    def test_round_limit_pause_and_self_exclusion(self):
        cfg = JetSettings.load()
        cfg.round_stake_limit = D('15')
        cfg.save()
        services.place_bet(player=self.player, stake='10', now=self.now)
        other, _ = _player('rudo')
        with self.assertRaisesMessage(services.JetError, 'round is full'):
            services.place_bet(player=other, stake='10', now=self.now)
        cfg.enabled = False
        cfg.save()
        with self.assertRaisesMessage(services.JetError, 'paused'):
            services.place_bet(player=other, stake='1', now=self.now)
        cfg.enabled = True
        cfg.save()
        other.self_excluded = True
        other.save(update_fields=['self_excluded'])
        with self.assertRaisesMessage(services.JetError, 'self-excluded'):
            services.place_bet(player=other, stake='1', now=self.now)

    def test_not_enough_balance(self):
        poor, _ = _player('poor', funds='1')
        with self.assertRaises(wallet_services.InsufficientFunds):
            services.place_bet(player=poor, stake='5', now=self.now)
        self.assertFalse(JetBet.objects.filter(player_id=poor.id).exists())

    def test_cancel_during_countdown_refunds(self):
        bet = services.place_bet(player=self.player, stake='10', now=self.now)
        services.cancel_bet(player_id=self.player.id, bet_id=bet.id, now=self.now)
        self.assertEqual(_balance(self.player), D('100.00'))
        services.start_flight(self.rnd.id, now=self.rnd.betting_ends_at)
        bet2 = JetBet.objects.create(round=self.rnd, player_id=self.player.id, display_name='x', slot=2, stake=D('1'))
        with self.assertRaises(services.JetError):
            services.cancel_bet(player_id=self.player.id, bet_id=bet2.id)


class FlightTests(TestCase):
    def setUp(self):
        self.player, _ = _player('farai')
        self.t0 = timezone.now()
        self.rnd = _round(crash='3.00', now=self.t0)
        self.bet = services.place_bet(player=self.player, stake='10', now=self.t0)
        self.start = self.rnd.betting_ends_at
        services.start_flight(self.rnd.id, now=self.start)

    def at(self, multiplier):
        return self.start + timedelta(seconds=engine.seconds_to(D(multiplier)) + 0.01)

    def test_manual_cash_out_by_server_clock(self):
        with self.assertRaisesMessage(services.JetError, 'hasn’t started'):
            other = _round(now=self.t0)
            b = services.place_bet(player=self.player, stake='1', now=self.t0)
            services.cash_out(player_id=self.player.id, bet_id=b.id, now=self.t0)
        bet = services.cash_out(player_id=self.player.id, bet_id=self.bet.id, now=self.at('2.00'))
        self.assertEqual((bet.status, bet.cashout_multiplier, bet.payout), ('cashed', D('2.00'), D('20.00')))
        with self.assertRaisesMessage(services.JetError, 'Already cashed out'):
            services.cash_out(player_id=self.player.id, bet_id=self.bet.id, now=self.at('2.10'))
        services.crash_round(self.rnd.id, now=self.at('3.00'))
        self.bet.refresh_from_db()
        self.assertEqual(self.bet.status, 'cashed')  # the crash leaves it alone
        self.assertEqual(_balance(self.player), D('100.00') - D('1') + D('10'))
        del other

    def test_too_late_after_the_crash_point(self):
        with self.assertRaisesMessage(services.JetError, 'Too late'):
            services.cash_out(player_id=self.player.id, bet_id=self.bet.id, now=self.at('3.20'))
        services.crash_round(self.rnd.id, now=self.at('3.00'))
        self.bet.refresh_from_db()
        self.assertEqual((self.bet.status, self.bet.payout), ('lost', D('0')))
        self.assertEqual(_balance(self.player), D('90.00'))

    def test_auto_cash_outs_and_crash_settlement(self):
        rnd = _round(crash='2.50', now=self.t0)
        a, _ = _player('auto_low')
        b, _ = _player('auto_high')
        c, _ = _player('auto_exact')
        low = services.place_bet(player=a, stake='10', auto_cashout='1.80', now=self.t0)
        high = services.place_bet(player=b, stake='10', auto_cashout='4.00', now=self.t0)
        exact = services.place_bet(player=c, stake='10', auto_cashout='2.50', now=self.t0)
        services.start_flight(rnd.id, now=rnd.betting_ends_at)
        start = rnd.betting_ends_at
        services.settle_auto_cashouts(rnd.id, now=start + timedelta(seconds=engine.seconds_to(D('2.00'))))
        low.refresh_from_db()
        self.assertEqual((low.status, low.cashout_multiplier, low.payout), ('cashed', D('1.80'), D('18.00')))
        services.crash_round(rnd.id, now=start + timedelta(seconds=engine.seconds_to(D('2.50'))))
        high.refresh_from_db()
        exact.refresh_from_db()
        self.assertEqual(high.status, 'lost')
        self.assertEqual((exact.status, exact.payout), ('cashed', D('25.00')))
        rnd.refresh_from_db()
        self.assertEqual((rnd.total_stake, rnd.total_payout), (D('30.00'), D('43.00')))

    def test_max_win_cashes_out_at_the_cap(self):
        cfg = JetSettings.load()
        cfg.max_win = D('25')
        cfg.save()
        services.crash_round(self.rnd.id, now=self.at('3.00'))  # crash 3.00, cap at 2.50x for $10
        self.bet.refresh_from_db()
        self.assertEqual((self.bet.status, self.bet.cashout_multiplier, self.bet.payout), ('cashed', D('2.50'), D('25.00')))


class RecoveryTests(TestCase):
    def test_restart_refunds_open_bets_and_settles_autos(self):
        p, _ = _player('restart')
        now = timezone.now()
        betting = _round(now=now)
        b1 = services.place_bet(player=p, stake='5', now=now)
        flying = _round(crash='3.00', now=now)
        auto = services.place_bet(player=p, stake='5', auto_cashout='2', now=now)
        manual = services.place_bet(player=p, stake='5', slot=2, now=now)
        services.start_flight(flying.id, now=now)
        self.assertEqual(services.recover(now=now), 2)
        for bet, status in ((b1, 'refunded'), (auto, 'cashed'), (manual, 'refunded')):
            bet.refresh_from_db()
            self.assertEqual(bet.status, status)
        self.assertEqual(_balance(p), D('100') - D('15') + D('5') + D('10') + D('5'))
        self.assertFalse(JetRound.objects.exclude(status='crashed').exists())
        del betting


class ApiTests(TestCase):
    def setUp(self):
        self.player, user = _player('apiplayer')
        self.api = APIClient()
        self.api.force_authenticate(user)
        self.rnd = _round(crash='5.00')

    def test_state_hides_the_crash_point_until_the_crash(self):
        res = self.api.post('/api/jet/bets/', {'stake': '2', 'slot': 1, 'auto_cashout': '2'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(res.json()['balance'], '98.00')
        state = APIClient().get('/api/jet/state/').json()
        self.assertIsNone(state['round']['crash_point'])
        self.assertIsNone(state['round']['server_seed'])
        self.assertEqual(state['bets'][0]['player'], 'a***r')
        self.assertNotIn('auto_cashout', state['bets'][0])
        mine = self.api.get('/api/jet/state/').json()['my_bets']
        self.assertEqual(mine[0]['auto_cashout'], '2.00')
        self.assertEqual(APIClient().get(f'/api/jet/rounds/{self.rnd.id}/').status_code, 404)
        services.crash_round(self.rnd.id)
        done = APIClient().get(f'/api/jet/rounds/{self.rnd.id}/').json()
        self.assertEqual(done['crash_point'], '5.00')
        self.assertEqual(engine.seed_hash(done['server_seed']), done['seed_hash'])

    def test_errors_are_player_friendly(self):
        res = self.api.post('/api/jet/bets/', {'stake': '1000', 'slot': 1}, format='json')
        self.assertEqual(res.status_code, 409)
        self.assertIn('Bets are', res.json()['detail'])
        broke = self.api.post('/api/jet/bets/', {'stake': '100', 'slot': 1}, format='json')
        self.assertEqual(broke.status_code, 201)
        res = self.api.post('/api/jet/bets/', {'stake': '5', 'slot': 2}, format='json')
        self.assertEqual(res.status_code, 402)

    def test_admin_settings_and_stats(self):
        admin = APIClient()
        admin.force_authenticate(User.objects.create_superuser('jetops', 'j@example.com', 'pw'))
        res = admin.put('/api/admin/jet/settings/', {'house_edge_percent': '4', 'max_bet': '50'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual(res.json()['rtp_percent'], '96.00')
        self.assertEqual(admin.put('/api/admin/jet/settings/', {'house_edge_percent': '40'}, format='json').status_code, 400)
        self.api.post('/api/jet/bets/', {'stake': '2', 'slot': 1}, format='json')
        stats = admin.get('/api/admin/jet/stats/').json()
        self.assertEqual(stats['live']['round'], self.rnd.id)
        self.assertNotIn('5.00', str(stats['live']))  # never the live crash point
        self.assertEqual(self.api.get('/api/admin/jet/stats/').status_code, 403)
