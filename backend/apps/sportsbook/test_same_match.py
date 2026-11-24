"""Several picks from one match on a multiple: different bets are fine (at the
same-match price); picks that contradict or overlap are refused."""
from decimal import Decimal as D

from django.test import SimpleTestCase, TestCase
from rest_framework.test import APIClient

from apps.sportsbook import services as sb
from apps.sportsbook.models import BetSlip, Event
from apps.sportsbook.same_match import Pick, relation
from apps.sportsbook.test_markets import _market, _outcome, _player
from apps.wallet import services as wallet_services
from apps.wallet.models import WalletRules


def mr(key):
    return Pick('mr', 'match_result', key=key)


def pk(market, kind, key, line=None, period='ft', metric='goals'):
    return Pick(market, kind, period=period, line=D(line) if line else None, key=key, metric=metric)


class RelationTests(SimpleTestCase):
    def test_overlapping_picks(self):
        self.assertEqual(relation(mr('home'), pk('dc', 'double_chance', '1x')), 'implies')
        self.assertEqual(relation(mr('home'), pk('dnb', 'draw_no_bet', 'home')), 'implies')
        self.assertEqual(relation(pk('a', 'over_under', 'over', '2.5'), pk('b', 'over_under', 'over', '1.5')), 'implies')
        self.assertEqual(relation(pk('cs', 'correct_score', '2:1'), mr('home')), 'implies')
        self.assertEqual(relation(pk('m', 'match_result', 'home'), mr('home')), 'implies')   # the same 1X2 in a market

    def test_contradicting_picks(self):
        self.assertEqual(relation(pk('a', 'over_under', 'over', '2.5'), pk('b', 'over_under', 'under', '1.5')), 'contradict')
        self.assertEqual(relation(mr('draw'), pk('w', 'win_to_nil_home', 'yes')), 'contradict')
        self.assertEqual(relation(mr('home'), mr('away')), 'same_market')

    def test_genuinely_different_picks(self):
        self.assertEqual(relation(mr('home'), pk('btts', 'btts', 'yes')), 'different')
        self.assertEqual(relation(mr('home'), pk('ou', 'over_under', 'over', '2.5')), 'different')
        self.assertEqual(relation(pk('ou', 'over_under', 'over', '2.5'), pk('oe', 'odd_even', 'odd')), 'different')
        self.assertEqual(relation(mr('home'), pk('ht', 'match_result', 'home', period='1h')), 'different')
        self.assertEqual(relation(mr('home'), pk('c', 'over_under', 'over', '9.5', metric='corners')), 'different')


class SameMatchMultipleTests(TestCase):
    def setUp(self):
        self.player = _player('smplayer')
        self.event = Event.objects.create(name='Chelsea v Arsenal', odds=D('2.00'), is_open=True)
        self.other = Event.objects.create(name='Spurs v Leeds', odds=D('1.50'), is_open=True)
        self.ou = _market(self.event, 'over_under', 'over_under:ft:2.5', [('over', '2.00'), ('under', '1.80')], line=D('2.5'))
        self.btts = _market(self.event, 'btts', 'btts:ft', [('yes', '1.80'), ('no', '2.00')])
        self.dc = _market(self.event, 'double_chance', 'double_chance:ft', [('1x', '1.30'), ('12', '1.25'), ('x2', '1.60')])

    def home(self, event=None, odds='2.00'):
        e = event or self.event
        return {'event': f'{e.name} home', 'odds': odds, 'event_id': e.id, 'selection': 'home'}

    def leg(self, market, key):
        o = _outcome(market, key)
        return {'event': f'{market.key} {key}', 'odds': str(o.odds), 'outcome_id': o.id}

    def place(self, *legs):
        return sb.place_accumulator(wallet='deposit', stake=D('10.00'), player_id=self.player.id, legs=list(legs))

    def test_overlapping_and_contradicting_picks_are_refused(self):
        with self.assertRaisesMessage(ValueError, 'one already includes the other'):
            self.place(self.home(), self.leg(self.dc, '1x'))
        with self.assertRaisesMessage(ValueError, 'same market'):
            self.place(self.leg(self.ou, 'over'), self.leg(self.ou, 'under'))

    def test_three_picks_from_one_match_and_one_from_another(self):
        slip = self.place(self.home(), self.leg(self.ou, 'over'), self.leg(self.btts, 'yes'), self.home(self.other, '1.50'))
        # (2.00 × 2.00 × 1.80 × 0.9²) × 1.50 = 8.748
        self.assertEqual(slip.combined_odds, D('8.75'))
        self.assertEqual(slip.legs.count(), 4)

    def test_settlement_applies_the_same_match_price_to_the_legs_that_won(self):
        slip = self.place(self.home(), self.leg(self.ou, 'over'), self.home(self.other, '1.50'))
        before = wallet_services.get_balance(self.player.id)
        sb.settle_event_from_score(self.other.id, home=1, away=0)
        sb.settle_event_from_score(self.event.id, home=3, away=1)
        slip.refresh_from_db()
        self.assertEqual(slip.status, BetSlip.Status.WON)
        self.assertEqual(slip.payout, D('54.00'))           # 10 × (2.00 × 2.00 × 0.9) × 1.50
        self.assertEqual(wallet_services.get_balance(self.player.id) - before, D('54.00'))

    def test_a_lost_pick_still_loses_the_ticket(self):
        slip = self.place(self.home(), self.leg(self.ou, 'over'))
        sb.settle_event_from_score(self.event.id, home=1, away=0)    # home won, under 2.5
        slip.refresh_from_db()
        self.assertEqual(slip.status, BetSlip.Status.LOST)

    def test_no_cash_out_on_same_match_multiples(self):
        from apps.sportsbook import cashout
        slip = self.place(self.home(), self.leg(self.ou, 'over'))
        self.assertIn('one match', cashout.slip_offer(slip).reason)

    def test_the_setting_can_switch_it_off_or_change_the_price(self):
        WalletRules.objects.update(same_match_price_percent=D('100'))
        self.assertEqual(self.place(self.home(), self.leg(self.ou, 'over')).combined_odds, D('4.00'))
        WalletRules.objects.update(same_match_bets=False)
        with self.assertRaisesMessage(ValueError, 'same match'):
            self.place(self.home(), self.leg(self.btts, 'yes'))

    def test_multibet_bonus_counts_a_match_once(self):
        self.assertEqual(sb.same_match_review([
            {'event_id': 1, 'odds': D('2'), 'pick': mr('home')},
            {'event_id': 1, 'odds': D('2'), 'pick': pk('ou', 'over_under', 'over', '2.5')},
            {'event_id': 2, 'odds': D('1.5'), 'pick': mr('home')},
        ])['per_match'], [D('3.60'), D('1.5')])

    def test_slip_check_endpoint(self):
        api = APIClient()
        ok = api.post('/api/betslips/check/', {'legs': [self.home(), self.leg(self.ou, 'over')]}, format='json').json()
        self.assertEqual((ok['problem'], ok['combined_odds'], ok['same_match_percent']), (None, '3.60', '90.00'))
        bad = api.post('/api/betslips/check/', {'legs': [self.home(), self.leg(self.dc, '1x')]}, format='json').json()
        self.assertEqual(bad['problem']['legs'], [0, 1])
        self.assertIn('overlap', bad['problem']['message'])


class CombinedMatchEntryTests(TestCase):
    """Picks from one match are one entry at one correlation-aware price; the ticket counts matches."""

    def setUp(self):
        from django.utils import timezone
        self.player = _player('combo')
        soon = timezone.now() + timezone.timedelta(days=1)
        self.event = Event.objects.create(name='Liverpool v Man United', odds=D('2.10'), odds_draw=D('3.40'),
                                          odds_away=D('3.50'), is_open=True, starts_at=soon, status='NS')
        self.other = Event.objects.create(name='Spurs v Leeds', odds=D('1.50'), odds_draw=D('4.00'), odds_away=D('6.00'),
                                          is_open=True, starts_at=soon, status='NS')
        self.ou = _market(self.event, 'over_under', 'over_under:ft:2.5', [('over', '1.90'), ('under', '1.90')], line=D('2.5'))
        self.btts = _market(self.event, 'btts', 'btts:ft', [('yes', '1.80'), ('no', '2.00')])

    def legs(self):
        return [{'event': 'Liverpool v Man United', 'odds': '2.10', 'event_id': self.event.id, 'selection': 'home'},
                {'event': 'btts yes', 'odds': '1.80', 'outcome_id': _outcome(self.btts, 'yes').id},
                {'event': 'over', 'odds': '1.90', 'outcome_id': _outcome(self.ou, 'over').id},
                {'event': 'Spurs v Leeds', 'odds': '1.50', 'event_id': self.other.id, 'selection': 'home'}]

    def test_the_slip_check_groups_by_match_with_names_and_one_price(self):
        from apps.sportsbook import correlation, services
        res = sb.check_accumulator(self.legs())
        self.assertEqual(res['fixtures'], 2)
        self.assertEqual(res['names'][:3], ['Liverpool Win', 'BTTS YES', 'Over 2.5 Goals'])
        first = next(m for m in res['matches'] if m['event_id'] == self.event.id)
        self.assertEqual(first['legs'], [0, 1, 2])
        product = D('2.10') * D('1.80') * D('1.90')
        self.assertLess(D(first['odds']), product)                         # priced for how they move together
        self.assertEqual(D(res['combined_odds']), (D(first['odds']) * D('1.50')).quantize(D('0.01')))

    def test_placed_ticket_stores_the_match_price_and_counts_matches(self):
        rules = WalletRules.load()
        rules.max_selections = 2                                           # 4 picks, but only 2 matches
        rules.save()
        slip = sb.place_accumulator(wallet='deposit', stake=D('5'), player_id=self.player.id, legs=self.legs())
        legs = list(slip.legs.order_by('id'))
        group = {leg.match_odds for leg in legs[:3]}
        self.assertEqual(len(group), 1)                                     # the same one price on each pick of the match
        self.assertEqual(legs[3].match_odds, D('1.50'))
        self.assertEqual(slip.combined_odds, (group.pop() * D('1.50')).quantize(D('0.01')))
        from apps.sportsbook.serializers import BetSlipSerializer
        data = BetSlipSerializer(slip).data
        self.assertEqual([leg['pick_name'] for leg in data['legs']], ['Liverpool Win', 'BTTS YES', 'Over 2.5 Goals', 'Spurs Win'])

    def test_the_match_limit_still_applies(self):
        rules = WalletRules.load()
        rules.max_selections = 1
        rules.save()
        with self.assertRaises(ValueError):
            sb.place_accumulator(wallet='deposit', stake=D('5'), player_id=self.player.id, legs=self.legs())
