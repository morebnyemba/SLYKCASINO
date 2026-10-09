"""Cash-out: offer pricing on singles and multiples, full and partial
cash-outs, the wallet credit, and settlement of what is left riding."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as account_services
from apps.sportsbook import cashout
from apps.sportsbook import services as sb
from apps.sportsbook.models import (
    Bet, BetLeg, BetSlip, Cashout, CashoutSettings, Event, Market, MarketOutcome,
)
from apps.wallet import services as wallet_services
from apps.wallet.models import LedgerEntry

D = Decimal


def _event(name, **kw):
    defaults = dict(starts_at=timezone.now() + timedelta(days=1), odds=D('2.00'), odds_draw=D('3.20'),
                    odds_away=D('3.80'), has_odds=True)
    defaults.update(kw)
    return Event.objects.create(name=name, **defaults)


def _player(username):
    player = account_services.create_player(username=username)
    user = User.objects.create(username=username)
    player.user = user
    player.save(update_fields=['user'])
    wallet_services.deposit(player_id=player.id, amount=D('100'), idempotency_key=f'seed:{username}')
    return player, user


def _balance(player):
    return wallet_services.get_balance_dto(player.id).balance


class OfferPricingTests(TestCase):
    def setUp(self):
        self.player, _ = _player('pricer')
        self.ev = _event('Dynamos vs CAPS United')

    def single(self, odds='2.00', stake='10'):
        return sb.place_bet(event=self.ev.name, stake=D(stake), odds=D(odds), player_id=self.player.id,
                            event_id=self.ev.id, selection='home')

    def test_value_follows_the_price_less_margin(self):
        bet = self.single()
        # Same price: stake back less the 5% margin.
        self.assertEqual(cashout.bet_offer(bet).value, D('9.50'))
        # Shortened to 1.25: 10 x 2.00 / 1.25 x 0.95 = 15.20.
        Event.objects.filter(pk=self.ev.pk).update(odds=D('1.25'))
        bet.refresh_from_db()
        self.assertEqual(cashout.bet_offer(bet).value, D('15.20'))
        # Drifted to 4.00: 10 x 2 / 4 x 0.95 = 4.75.
        Event.objects.filter(pk=self.ev.pk).update(odds=D('4.00'))
        bet.refresh_from_db()
        self.assertEqual(cashout.bet_offer(bet).value, D('4.75'))

    def test_no_offer_when_market_cannot_be_priced(self):
        bet = self.single()
        Event.objects.filter(pk=self.ev.pk).update(is_open=False)
        bet.refresh_from_db()
        offer = cashout.bet_offer(bet)
        self.assertFalse(offer.available)
        self.assertIn('suspended', offer.reason)
        # Past kick-off without in-play trading: no stale pre-match price.
        Event.objects.filter(pk=self.ev.pk).update(is_open=True, starts_at=timezone.now() - timedelta(minutes=5))
        bet.refresh_from_db()
        self.assertFalse(cashout.bet_offer(bet).available)

    def test_switched_off_and_minimum(self):
        bet = self.single(stake='1')
        self.assertFalse(cashout.bet_offer(bet).available)  # 0.95 < $1 minimum
        cfg = CashoutSettings.load()
        cfg.min_amount = D('0.50')
        cfg.save()
        self.assertTrue(cashout.bet_offer(bet).available)
        cfg.enabled = False
        cfg.save()
        self.assertFalse(cashout.bet_offer(bet).available)

    def test_secondary_market_outcome(self):
        market = Market.objects.create(event=self.ev, key='btts:ft', name='Both teams to score', group='goals', kind='btts')
        yes = MarketOutcome.objects.create(market=market, key='yes', label='Yes', odds=D('1.80'))
        bet = sb.place_bet(event='BTTS', stake=D('10'), odds=D('1.80'), player_id=self.player.id, outcome_id=yes.id)
        MarketOutcome.objects.filter(pk=yes.pk).update(odds=D('1.20'))
        bet.refresh_from_db()
        self.assertEqual(cashout.bet_offer(bet).value, D('14.25'))  # 10 x 1.8 / 1.2 x 0.95
        MarketOutcome.objects.filter(pk=yes.pk).update(is_open=False)
        bet.refresh_from_db()
        self.assertFalse(cashout.bet_offer(bet).available)

    def test_multiple_banks_won_legs_and_dies_on_a_lost_one(self):
        other = _event('Highlanders vs FC Platinum', odds=D('1.50'))
        slip = sb.place_accumulator(stake=D('10'), player_id=self.player.id, legs=[
            {'event': self.ev.name, 'event_id': self.ev.id, 'selection': 'home', 'odds': D('2.00')},
            {'event': other.name, 'event_id': other.id, 'selection': 'home', 'odds': D('1.50')},
        ])
        # Both open at the prices taken: 10 x 3.0 / 3.0 x 0.95.
        self.assertEqual(cashout.slip_offer(slip).value, D('9.50'))
        # First leg wins: banked at 2.00; second still 1.50 -> 10 x 3 / 1.5 x 0.95 = 19.00.
        BetLeg.objects.filter(slip=slip, event_ref=self.ev).update(result=BetLeg.Result.WON)
        self.assertEqual(cashout.slip_offer(slip).value, D('19.00'))
        BetLeg.objects.filter(slip=slip, event_ref=other).update(result=BetLeg.Result.LOST)
        self.assertFalse(cashout.slip_offer(slip).available)


class CashOutApiTests(TestCase):
    def setUp(self):
        self.player, user = _player('casher')
        self.api = APIClient()
        self.api.force_authenticate(user)
        self.ev = _event('Dynamos vs CAPS United')
        self.bet = sb.place_bet(event=self.ev.name, stake=D('10'), odds=D('2.00'), player_id=self.player.id,
                                event_id=self.ev.id, selection='home')
        Event.objects.filter(pk=self.ev.pk).update(odds=D('1.25'))  # offer now 15.20

    def test_offer_is_on_the_ticket_and_the_offers_endpoint(self):
        ticket = self.api.get('/api/bets/').json()['results'][0]
        self.assertEqual(ticket['cashout']['value'], '15.20')
        self.assertTrue(ticket['cashout']['partial'])
        offers = self.api.get(f'/api/cashout/offers/?bets={self.bet.id}').json()
        self.assertEqual(offers['bets'][str(self.bet.id)]['value'], '15.20')

    def test_full_cash_out_pays_once_and_closes_the_ticket(self):
        before = _balance(self.player)
        res = self.api.post(f'/api/bets/{self.bet.id}/cashout/', {'expected': '15.20'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertEqual((res.json()['paid'], res.json()['full']), ('15.20', True))
        self.assertEqual(_balance(self.player), before + D('15.20'))
        self.bet.refresh_from_db()
        self.assertEqual((self.bet.status, self.bet.payout, self.bet.stake_cashed_out), ('cashed_out', D('15.20'), D('10')))
        # A second attempt is refused and settlement leaves it alone.
        again = self.api.post(f'/api/bets/{self.bet.id}/cashout/', {'expected': '15.20'}, format='json')
        self.assertEqual(again.status_code, 409)
        sb.settle_event(self.ev.id, 'home')
        self.bet.refresh_from_db()
        self.assertEqual(self.bet.status, 'cashed_out')
        self.assertEqual(_balance(self.player), before + D('15.20'))
        self.assertEqual(LedgerEntry.objects.filter(reference__endswith=':cashout').count(), 1)

    def test_value_dropped_since_the_player_saw_it(self):
        Event.objects.filter(pk=self.ev.pk).update(odds=D('1.60'))  # now 11.87
        res = self.api.post(f'/api/bets/{self.bet.id}/cashout/', {'expected': '15.20'}, format='json')
        self.assertEqual(res.status_code, 409)
        self.assertEqual((res.json()['code'], res.json()['value']), ('cashout_changed', '11.87'))
        self.bet.refresh_from_db()
        self.assertEqual(self.bet.status, 'open')

    def test_partial_cash_out_leaves_the_rest_riding(self):
        before = _balance(self.player)
        res = self.api.post(f'/api/bets/{self.bet.id}/cashout/', {'expected': '15.20', 'amount': '7.60'}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        self.assertFalse(res.json()['full'])
        self.bet.refresh_from_db()
        self.assertEqual((self.bet.status, self.bet.stake, self.bet.stake_cashed_out), ('open', D('5.00'), D('5.00')))
        # The remaining $5 wins at the original 2.00.
        sb.settle_event(self.ev.id, 'home')
        self.bet.refresh_from_db()
        self.assertEqual((self.bet.status, self.bet.payout), ('won', D('10.00')))
        self.assertEqual(_balance(self.player), before + D('7.60') + D('10.00'))

    def test_partial_limits(self):
        too_small = self.api.post(f'/api/bets/{self.bet.id}/cashout/', {'expected': '15.20', 'amount': '0.50'}, format='json')
        self.assertEqual(too_small.status_code, 409)
        leaves_too_little = self.api.post(f'/api/bets/{self.bet.id}/cashout/', {'expected': '15.20', 'amount': '14.80'}, format='json')
        self.assertEqual(leaves_too_little.status_code, 409)
        cfg = CashoutSettings.load()
        cfg.allow_partial = False
        cfg.save()
        off = self.api.post(f'/api/bets/{self.bet.id}/cashout/', {'expected': '15.20', 'amount': '5'}, format='json')
        self.assertEqual(off.status_code, 409)
        self.assertFalse(Cashout.objects.exists())

    def test_cannot_cash_out_someone_elses_ticket(self):
        _, other = _player('nosy')
        api = APIClient()
        api.force_authenticate(other)
        res = api.post(f'/api/bets/{self.bet.id}/cashout/', {'expected': '15.20'}, format='json')
        self.assertEqual(res.status_code, 409)
        self.bet.refresh_from_db()
        self.assertEqual(self.bet.status, 'open')

    def test_multiple_full_cash_out(self):
        other = _event('Highlanders vs FC Platinum', odds=D('1.50'))
        slip = sb.place_accumulator(stake=D('10'), player_id=self.player.id, legs=[
            {'event': other.name, 'event_id': other.id, 'selection': 'home', 'odds': D('1.50')},
            {'event': 'Bosso v Chicken Inn', 'event_id': _event('Bosso v Chicken Inn').id, 'selection': 'home', 'odds': D('2.00')},
        ])
        value = self.api.get('/api/betslips/').json()['results'][0]['cashout']['value']
        res = self.api.post(f'/api/betslips/{slip.id}/cashout/', {'expected': value}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        slip.refresh_from_db()
        self.assertEqual(slip.status, BetSlip.Status.CASHED_OUT)


class AdminCashoutSettingsTests(TestCase):
    def setUp(self):
        self.api = APIClient()
        self.api.force_authenticate(User.objects.create_superuser('cashops', 'c@example.com', 'pw'))

    def test_read_and_update(self):
        data = self.api.get('/api/admin/sportsbook/cashout/').json()
        self.assertTrue(data['enabled'])
        self.assertEqual(data['margin_percent'], '5.00')
        res = self.api.put('/api/admin/sportsbook/cashout/', {'margin_percent': '8', 'allow_partial': False}, format='json')
        self.assertEqual(res.status_code, 200, res.content)
        cfg = CashoutSettings.load()
        self.assertEqual((cfg.margin_percent, cfg.allow_partial), (D('8'), False))
        self.assertEqual(self.api.put('/api/admin/sportsbook/cashout/', {'margin_percent': '80'}, format='json').status_code, 400)

    def test_players_cannot_change_it(self):
        _, user = _player('sneaky')
        api = APIClient()
        api.force_authenticate(user)
        self.assertEqual(api.put('/api/admin/sportsbook/cashout/', {'enabled': False}, format='json').status_code, 403)
