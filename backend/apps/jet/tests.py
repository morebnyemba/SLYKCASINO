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

from . import bot_chat, bots, engine, services, social
from .models import JetBet, JetChatMessage, JetFreeBet, JetRound, JetSettings

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


class BotTests(TestCase):
    """Simulated players fill the live list but are never money: nothing is
    stored, so no report, total or analytics figure can include them."""

    def setUp(self):
        cfg = JetSettings.load()
        cfg.bots_enabled, cfg.bot_count = True, 1000
        cfg.save()
        self.player, user = _player('realone')
        self.api = APIClient()
        self.api.force_authenticate(user)

    def test_off_by_default_and_when_disabled(self):
        JetSettings.objects.all().delete()
        self.assertEqual(bots.plan(_round()), ())

    def test_deterministic_capped_and_within_limits(self):
        rnd = _round()
        plan = bots.plan(rnd)
        self.assertEqual(plan, bots.plan(rnd))
        self.assertTrue(700 <= len(plan) <= 1000)
        cfg = JetSettings.load()
        self.assertTrue(all(cfg.min_bet <= b.stake <= cfg.max_bet and b.id < 0 for b in plan))
        self.assertEqual(len({b.id for b in plan}), len(plan))

    def test_bots_never_touch_money_or_records(self):
        from apps.wallet.models import LedgerEntry
        from apps.wallet import reporting
        ledger_before = LedgerEntry.objects.count()
        rnd = _round(crash='3.00')
        res = self.api.post('/api/jet/bets/', {'stake': '2', 'slot': 1, 'auto_cashout': '2'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)

        # Betting: bots arrive over the countdown and appear in the list.
        later = rnd.created_at + timedelta(seconds=10)
        state_bets = bots.snapshot(rnd, later)
        self.assertGreater(len(state_bets), 500)
        listed = APIClient().get('/api/jet/state/').json()['bets']
        self.assertIn('r***e', [b['player'] for b in listed])

        services.start_flight(rnd.id)
        services.crash_round(rnd.id)
        rnd.refresh_from_db()
        done = bots.snapshot(rnd, timezone.now())
        cashed = [b for b in done if b['status'] == 'cashed']
        self.assertTrue(cashed and all(D(b['cashout_multiplier']) <= D('3.00') for b in cashed))
        self.assertTrue(all(b['status'] in ('cashed', 'lost') for b in done))

        # Only the real player's bet exists anywhere that counts.
        self.assertEqual(JetBet.objects.count(), 1)
        self.assertEqual((rnd.bet_count, rnd.total_stake, rnd.total_payout), (1, D('2.00'), D('4.00')))
        self.assertEqual(LedgerEntry.objects.count(), ledger_before + 2)  # stake + payout
        kpis = reporting.ledger_kpis(None, None, timezone.now() + timedelta(seconds=1))
        self.assertEqual((kpis['casino']['plays'], kpis['casino']['stakes'], kpis['casino']['ggr']), (1, '2.00', '-2.00'))

        admin = APIClient()
        admin.force_authenticate(User.objects.create_superuser('ops', 'o@example.com', 'pw'))
        stats = admin.get('/api/admin/jet/stats/').json()
        self.assertEqual((stats['today']['bets'], D(stats['today']['stake']), stats['players_today']), (1, D('2'), 1))
        self.assertTrue(stats['bots']['enabled'])

    def test_admin_controls(self):
        admin = APIClient()
        admin.force_authenticate(User.objects.create_superuser('ops2', 'o2@example.com', 'pw'))
        self.assertEqual(admin.put('/api/admin/jet/settings/', {'bot_count': 1001}, format='json').status_code, 400)
        res = admin.put('/api/admin/jet/settings/', {'bots_enabled': False, 'bot_count': 250}, format='json').json()
        self.assertEqual((res['bots_enabled'], res['bot_count']), (False, 250))
        self.assertFalse(APIClient().get('/api/jet/state/').json()['settings']['bots_enabled'])


class FreeBetTests(TestCase):
    """Free bets: no stake taken, winnings only (as a bonus), kept out of
    round totals and gaming figures."""

    def setUp(self):
        self.player, _ = _player('freddy', funds='10')
        self.rnd = _round(crash='3.00')

    def free(self, amount='1.00', **kw):
        return JetFreeBet.objects.create(player_id=self.player.id, amount=D(amount),
                                         expires_at=timezone.now() + timedelta(hours=1), **kw)

    def test_win_pays_winnings_as_bonus_and_skips_totals(self):
        from apps.wallet.models import LedgerEntry
        fb = self.free('2.00')
        bet = services.place_bet(player=self.player, slot=1, auto_cashout='2', free_bet_id=fb.id)
        self.assertTrue(bet.is_free)
        self.assertEqual(_balance(self.player), D('10.00'))  # nothing taken
        fb.refresh_from_db()
        self.assertEqual((fb.status, fb.bet_id), ('used', bet.id))
        with self.assertRaises(services.JetError):
            services.place_bet(player=self.player, slot=2, free_bet_id=fb.id)  # can't reuse
        services.start_flight(self.rnd.id)
        services.crash_round(self.rnd.id)
        bet.refresh_from_db()
        self.rnd.refresh_from_db()
        self.assertEqual((bet.status, bet.payout), ('cashed', D('2.00')))   # 2.00 x 2 - 2.00 stake
        self.assertEqual(_balance(self.player), D('12.00'))
        self.assertEqual((self.rnd.bet_count, self.rnd.total_stake, self.rnd.total_payout), (0, D('0'), D('0')))
        kinds = set(LedgerEntry.objects.filter(wallet__player_id=self.player.id).values_list('kind', flat=True))
        self.assertEqual(kinds, {'deposit', 'bonus'})

    def test_cancel_returns_the_free_bet_and_expired_ones_fail(self):
        fb = self.free()
        bet = services.place_bet(player=self.player, slot=1, free_bet_id=fb.id)
        services.cancel_bet(player_id=self.player.id, bet_id=bet.id)
        fb.refresh_from_db()
        self.assertEqual((fb.status, fb.bet_id), ('available', None))
        stale = JetFreeBet.objects.create(player_id=self.player.id, amount=D('1'), expires_at=timezone.now() - timedelta(minutes=1))
        with self.assertRaisesMessage(services.JetError, 'expired'):
            services.place_bet(player=self.player, slot=2, free_bet_id=stale.id)


class ChatAndRainTests(TestCase):
    def setUp(self):
        self.player, user = _player('chatty')
        self.api = APIClient()
        self.api.force_authenticate(user)

    def say(self, body):
        return self.api.post('/api/jet/chat/', {'body': body}, format='json')

    def test_chat_rules(self):
        self.assertEqual(self.say('hello pilots').status_code, 201)
        self.assertEqual(self.say('again').status_code, 409)  # too fast
        JetChatMessage.objects.update(created_at=timezone.now() - timedelta(seconds=10))
        self.assertIn('Links', self.say('join www.spam.com').json()['detail'])
        self.assertIn('Links', self.say('call 0771 234 567').json()['detail'])
        self.assertEqual(self.say('x' * 200).status_code, 409)
        listed = APIClient().get('/api/jet/chat/').json()['messages']
        self.assertEqual([(m['name'], m['body']) for m in listed], [('c***y', 'hello pilots')])

        broke, broke_user = account_services.create_player(username='nodep'), User.objects.create(username='nodep')
        broke.user = broke_user
        broke.save(update_fields=['user'])
        api = APIClient()
        api.force_authenticate(broke_user)
        self.assertIn('first deposit', api.post('/api/jet/chat/', {'body': 'hi'}, format='json').json()['detail'])

    def test_admin_hide_and_mute(self):
        self.say('rude words')
        admin = APIClient()
        admin.force_authenticate(User.objects.create_superuser('mod', 'm@example.com', 'pw'))
        msg = admin.get('/api/admin/jet/chat/').json()['results'][0]
        self.assertEqual(msg['player_id'], self.player.id)
        self.assertEqual(admin.post(f"/api/admin/jet/chat/{msg['id']}/hide/").status_code, 200)
        self.assertEqual(APIClient().get('/api/jet/chat/').json()['messages'], [])
        admin.post('/api/admin/jet/chat/mute/', {'player_id': self.player.id, 'hours': 2}, format='json')
        JetChatMessage.objects.update(created_at=timezone.now() - timedelta(seconds=10))
        self.assertIn('muted', self.say('let me back').json()['detail'])

    def test_win_bot_announces_big_wins_only(self):
        rnd = _round(crash='30.00')
        services.place_bet(player=self.player, stake='1', slot=1, auto_cashout='1.5')
        services.place_bet(player=self.player, stake='2', slot=2, auto_cashout='12')
        services.start_flight(rnd.id)
        services.crash_round(rnd.id)
        msg = social.announce_round(rnd)
        self.assertEqual((msg.kind, msg.name), ('win', social.BOT_NAME))
        self.assertIn('c***y cashed out at 12.00x and won $24.00', msg.body)
        small = _round(crash='1.20')
        self.assertIsNone(social.announce_round(small))

    def test_rain_goes_to_active_depositors_within_budget(self):
        cfg = JetSettings.load()
        cfg.rain_daily_budget = D('3.00')
        cfg.save()
        self.say('anyone here?')
        lurker, _ = _player('lurker')  # deposited but not active
        res = social.rain(players=10, amount='1.00')
        self.assertEqual(res['given'], 1)
        self.assertEqual(list(JetFreeBet.objects.values_list('player_id', flat=True)), [self.player.id])
        self.assertTrue(JetChatMessage.objects.filter(kind='rain', body__contains='c***y').exists())
        state = self.api.get('/api/jet/state/').json()
        self.assertEqual([f['amount'] for f in state['free_bets']], ['1.00'])
        social.rain(players=10, amount='1.00')
        social.rain(players=10, amount='1.00')
        self.assertIn('budget', social.rain(players=10, amount='1.00')['reason'])
        self.assertEqual(social.given_today(), D('3.00'))

    def test_auto_rain_schedule_and_admin_button(self):
        self.say('hi')
        cfg = JetSettings.load()
        cfg.rain_enabled, cfg.rain_every_minutes = True, 30
        cfg.save()
        self.assertEqual(social.maybe_auto_rain()['given'], 1)
        self.assertIsNone(social.maybe_auto_rain())  # not due yet
        admin = APIClient()
        admin.force_authenticate(User.objects.create_superuser('boss', 'b@example.com', 'pw'))
        res = admin.post('/api/admin/jet/rain/', {'players': 5, 'amount': '0.50'}, format='json')
        self.assertEqual((res.status_code, res.json()['given']), (200, 1))
        self.assertEqual(self.api.post('/api/admin/jet/rain/', {}, format='json').status_code, 403)


class BotChatTests(TestCase):
    """Simulated players' chatter and its guardrails."""

    def setUp(self):
        cfg = JetSettings.load()
        cfg.bots_enabled, cfg.bot_count, cfg.bot_chat_enabled, cfg.bot_chat_per_minute = True, 200, True, 6
        cfg.save()
        self.rnd = _round(crash='15.00')

    def test_off_unless_every_switch_is_on(self):
        JetSettings.objects.update(bot_chat_enabled=False)
        self.assertEqual(bot_chat.speak(self.rnd, 'betting', 600), [])
        JetSettings.objects.update(bot_chat_enabled=True, bots_enabled=False)
        self.assertEqual(bot_chat.speak(self.rnd, 'betting', 600), [])

    def test_rate_kind_and_names(self):
        said = bot_chat.speak(self.rnd, 'betting', 60, rng=random.Random(3))
        self.assertEqual(len(said), 6)  # 6 a minute
        names = {b.name for b in bots.plan(self.rnd)}
        for m in said:
            self.assertEqual((m.kind, m.player_id), ('bot', None))
            self.assertIn(m.name, names)
            self.assertIn(m.body, bot_chat.GREETINGS)
        services.start_flight(self.rnd.id)
        rnd = services.crash_round(self.rnd.id)
        self.assertTrue(all(m.body in bot_chat.HIGH for m in bot_chat.speak(rnd, 'crashed', 60)))
        JetSettings.objects.update(bot_chat_per_minute=500)
        self.assertLessEqual(len(bot_chat.speak(rnd, 'crashed', 60)), bot_chat.MAX_PER_MINUTE)

    def test_real_chat_comes_first(self):
        player, _ = _player('talker')
        for i in range(3):
            JetChatMessage.objects.create(player_id=player.id, name='t***r', body=f'hello {i}')
        self.assertEqual(bot_chat.speak(self.rnd, 'betting', 120), [])
        JetChatMessage.objects.filter(body__in=['hello 1', 'hello 2']).delete()
        cfg = JetSettings.load()
        self.assertEqual(bot_chat.lines_due(cfg, 60, real=1), 3.0)  # halved

    def test_lines_never_push_play_claim_money_or_name_anyone(self):
        banned = ('deposit', 'bet ', 'bet!', 'more', 'bigger', 'go big', 'all in', 'won', 'win', '$', 'balance',
                  'cash out', 'chase', 'profit', 'up ', '@')
        for line in bot_chat.ALL_LINES:
            low = line.lower()
            self.assertFalse(any(word in low for word in banned), line)
            self.assertNotIn('***', line)

    def test_prune_and_moderation_label(self):
        msg = JetChatMessage.objects.create(kind='bot', name='a***b', body='gl all')
        JetChatMessage.objects.filter(pk=msg.pk).update(created_at=timezone.now() - timedelta(hours=7))
        self.assertEqual(bot_chat.prune(), 1)
        bot_chat.speak(self.rnd, 'betting', 30)
        admin = APIClient()
        admin.force_authenticate(User.objects.create_superuser('mod2', 'm2@example.com', 'pw'))
        rows = admin.get('/api/admin/jet/chat/').json()['results']
        self.assertTrue(rows and all((r['kind'], r['player_id']) == ('bot', None) for r in rows))
