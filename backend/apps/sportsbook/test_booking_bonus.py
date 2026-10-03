"""Booking codes (share a slip by code, re-priced on load) and the multi-bet
bonus (tiered by qualifying legs, paid on top of a winning multiple)."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal

from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from apps.accounts import services as account_services
from apps.sportsbook import booking
from apps.sportsbook import services as sb
from apps.sportsbook.models import BookingCode, Event, Market, MarketOutcome, MultiBetBonusTier
from apps.wallet import services as wallet_services
from apps.wallet.models import LedgerEntry

D = Decimal


def _event(name, **kw):
    defaults = dict(
        starts_at=timezone.now() + timedelta(days=1),
        odds=D('2.00'), odds_draw=D('3.20'), odds_away=D('3.80'),
    )
    defaults.update(kw)
    return Event.objects.create(name=name, **defaults)


class BookingCodeTests(TestCase):
    def setUp(self):
        self.a = _event('Dynamos vs CAPS United')
        self.b = _event('Highlanders vs FC Platinum')
        market = Market.objects.create(event=self.b, key='btts:ft', name='Both teams to score',
                                       group='goals', kind='btts')
        self.yes = MarketOutcome.objects.create(market=market, key='yes', label='Yes', odds=D('1.85'))
        self.api = APIClient()

    def test_book_and_load_round_trip(self):
        res = self.api.post('/api/booking-codes/', {'selections': [
            {'event_id': self.a.id, 'selection': 'home'},
            {'outcome_id': self.yes.id},
            {'event_id': self.a.id, 'selection': 'home'},  # duplicate: dropped
            {'event_id': 999999, 'selection': 'home'},     # unknown: dropped
            {'event_id': self.b.id, 'selection': 'bogus'},  # malformed: dropped
        ]}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        code = res.json()['code']
        self.assertEqual(len(code), booking.CODE_LENGTH)
        self.assertEqual(len(res.json()['legs']), 2)

        loaded = self.api.get(f'/api/booking-codes/{code.lower()}/').json()
        self.assertEqual(loaded['available'], 2)
        home, btts = loaded['legs']
        self.assertEqual((home['event_id'], home['selection'], home['odds']), (self.a.id, 'home', '2.00'))
        self.assertEqual((btts['outcome_id'], btts['market_name'], btts['outcome_label']), (self.yes.id, 'Both teams to score', 'Yes'))
        self.assertEqual(BookingCode.objects.get(code=code).loads, 1)

    def test_load_reprices_and_flags_closed_picks(self):
        code = booking.create_booking([
            {'event_id': self.a.id, 'selection': 'away'}, {'outcome_id': self.yes.id},
        ]).code
        Event.objects.filter(pk=self.a.id).update(odds_away=D('4.50'))
        MarketOutcome.objects.filter(pk=self.yes.id).update(is_open=False)
        legs = booking.load_booking(code)['legs']
        self.assertEqual(legs[0]['odds'], '4.50')
        self.assertTrue(legs[0]['available'])
        self.assertFalse(legs[1]['available'])

    def test_rejects_empty_and_unknown_code(self):
        self.assertEqual(self.api.post('/api/booking-codes/', {'selections': []}, format='json').status_code, 400)
        self.assertEqual(self.api.get('/api/booking-codes/NOPE00/').status_code, 404)

    def test_codes_avoid_ambiguous_characters(self):
        for _ in range(50):
            self.assertFalse(set(booking._new_code()) & set('01OIL'))


@override_settings(SPORTSBOOK_ACCA_BONUS_MIN_ODDS='1.20', SPORTSBOOK_ACCA_BONUS_CAP='1000')
class MultiBetBonusTests(TestCase):
    def setUp(self):
        MultiBetBonusTier.objects.all().delete()
        MultiBetBonusTier.objects.create(min_legs=3, percent=D('5'))
        MultiBetBonusTier.objects.create(min_legs=4, percent=D('10'))
        self.events = [_event(f'Match {i}') for i in range(4)]
        self.player = account_services.create_player(username='acca_punter')
        wallet_services.credit(player_id=self.player.id, amount=D('100'), kind='deposit', idempotency_key='acca:dep')

    def _place(self, odds, stake='10'):
        legs = [
            {'event': ev.name, 'event_id': ev.id, 'selection': 'home', 'odds': o}
            for ev, o in zip(self.events, odds)
        ]
        for ev, o in zip(self.events, odds):
            Event.objects.filter(pk=ev.id).update(odds=D(o))
        return sb.place_accumulator(stake=D(stake), legs=legs, player_id=self.player.id)

    def test_tier_from_qualifying_legs_only(self):
        self.assertEqual(sb.multibet_bonus_percent([D('2'), D('2')]), D('0'))
        self.assertEqual(sb.multibet_bonus_percent([D('2'), D('2'), D('2')]), D('5'))
        self.assertEqual(sb.multibet_bonus_percent([D('2'), D('2'), D('2'), D('2')]), D('10'))
        # A 1.10 leg doesn't count towards a tier.
        self.assertEqual(sb.multibet_bonus_percent([D('2'), D('2'), D('2'), D('1.10')]), D('5'))

    def test_winning_slip_pays_bonus_on_winnings(self):
        slip = self._place(['2.00', '2.00', '2.00', '2.00'])
        self.assertEqual(slip.bonus_percent, D('10'))
        for ev in self.events:
            sb.settle_event(ev.id, 'home')
        slip.refresh_from_db()
        # Payout 10 x 16 = 160; winnings 150; bonus 10% = 15.
        self.assertEqual((slip.status, slip.payout, slip.bonus), ('won', D('160.00'), D('15.00')))
        self.assertEqual(wallet_services.get_balance(self.player.id), D('265.00'))
        bonus_entry = LedgerEntry.objects.get(kind='bonus', reference=f'slip:{slip.id}:multibet-bonus')
        self.assertEqual(bonus_entry.amount, D('15.00'))
        # Re-settling never pays twice.
        sb._settle_slip_if_ready(slip.id)
        self.assertEqual(wallet_services.get_balance(self.player.id), D('265.00'))

    def test_void_leg_drops_the_tier(self):
        slip = self._place(['2.00', '2.00', '2.00', '2.00'])
        for ev in self.events[:3]:
            sb.settle_event(ev.id, 'home')
        sb.settle_event(self.events[3].id, 'void')
        slip.refresh_from_db()
        # Three winning legs: 10 x 8 = 80, winnings 70, 3-leg tier 5% = 3.50.
        self.assertEqual((slip.payout, slip.bonus), (D('80.00'), D('3.50')))

    def test_lost_slip_pays_no_bonus(self):
        slip = self._place(['2.00', '2.00', '2.00', '2.00'])
        sb.settle_event(self.events[0].id, 'away')
        for ev in self.events[1:]:
            sb.settle_event(ev.id, 'home')
        slip.refresh_from_db()
        self.assertEqual((slip.status, slip.bonus), ('lost', D('0')))
        self.assertFalse(LedgerEntry.objects.filter(kind='bonus').exists())

    @override_settings(SPORTSBOOK_ACCA_BONUS_CAP='5')
    def test_bonus_is_capped(self):
        slip = self._place(['2.00', '2.00', '2.00', '2.00'])
        for ev in self.events:
            sb.settle_event(ev.id, 'home')
        slip.refresh_from_db()
        self.assertEqual(slip.bonus, D('5.00'))

    def test_ladder_endpoint(self):
        data = APIClient().get('/api/multibet-bonus/').json()
        self.assertEqual(data['min_odds'], '1.20')
        self.assertEqual([t['min_legs'] for t in data['tiers']], [3, 4])

