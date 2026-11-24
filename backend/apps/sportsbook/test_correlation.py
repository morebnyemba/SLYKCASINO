from decimal import Decimal as D

from django.test import TestCase
from django.utils import timezone

from apps.sportsbook import correlation
from apps.sportsbook.models import Event, Market, MarketOutcome
from apps.sportsbook.same_match import Pick

HOME = Pick(market='mr', kind='match_result', key='home', name='Home')
DRAW = Pick(market='mr', kind='match_result', key='draw', name='Draw')
OVER = Pick(market='ou', kind='over_under', line=D('2.5'), key='over', name='Over 2.5')
UNDER = Pick(market='ou', kind='over_under', line=D('2.5'), key='under', name='Under 2.5')
GG = Pick(market='bt', kind='btts', key='yes', name='BTTS yes')
NG = Pick(market='bt', kind='btts', key='no', name='BTTS no')
CORNERS = Pick(market='co', kind='manual', key='over', name='Over 8.5 corners')


class CorrelationPricingTests(TestCase):
    """Same-match prices follow how much the picks move together, from the match's own goals model."""

    def setUp(self):
        self.e = Event.objects.create(name='Liverpool vs Man United', starts_at=timezone.now() + timezone.timedelta(days=1),
                                      status='NS', odds=D('2.10'), odds_draw=D('3.40'), odds_away=D('3.50'))
        ou = Market.objects.create(event=self.e, key='ou:2.5', name='Over/Under 2.5', kind='over_under', line=D('2.5'))
        MarketOutcome.objects.create(market=ou, key='over', label='Over 2.5', odds=D('1.90'))
        MarketOutcome.objects.create(market=ou, key='under', label='Under 2.5', odds=D('1.90'))

    def price(self, *legs):
        return correlation.group_price(self.e, list(legs), D('90'))

    def test_the_model_reproduces_the_match_prices(self):
        lh, la = correlation.fit(self.e)
        self.assertGreater(lh, la)                                  # the favourite scores more
        self.assertAlmostEqual(lh + la, 2.6, delta=0.35)            # ~50/50 over 2.5

    def test_prices_follow_the_correlation(self):
        home_over = self.price((HOME, D('2.10')), (OVER, D('1.90')))      # move together: cut
        draw_under = self.price((DRAW, D('3.40')), (UNDER, D('1.90')))    # move strongly together: cut more
        home_gg = self.price((HOME, D('2.10')), (GG, D('1.80')))          # barely related: close to the product
        self.assertLess(home_over, D('2.10') * D('1.90'))
        self.assertLess(draw_under / (D('3.40') * D('1.90')), home_over / (D('2.10') * D('1.90')))
        self.assertGreater(home_gg / (D('2.10') * D('1.80')), draw_under / (D('3.40') * D('1.90')))

    def test_never_above_the_product_nor_below_the_longest_price(self):
        for legs in (((HOME, D('2.10')), (NG, D('2.00'))), ((DRAW, D('3.40')), (UNDER, D('1.90'))),
                     ((GG, D('1.80')), (OVER, D('1.90')))):
            p = self.price(*legs)
            product = legs[0][1] * legs[1][1]
            self.assertLessEqual(p, product)
            self.assertGreaterEqual(p, max(o for _, o in legs))

    def test_unmeasurable_picks_take_the_flat_rate(self):
        p = self.price((HOME, D('2.10')), (CORNERS, D('1.80')))
        self.assertEqual(p, (D('2.10') * D('1.80') * D('0.90')).quantize(D('0.01')))

    def test_in_play_falls_back_to_the_flat_rate(self):
        p = correlation.group_price(self.e, [(HOME, D('2.10')), (OVER, D('1.90'))], D('90'), in_play=True)
        self.assertEqual(p, (D('2.10') * D('1.90') * D('0.90')).quantize(D('0.01')))

    def test_one_pick_is_its_own_price(self):
        self.assertEqual(self.price((HOME, D('2.10'))), D('2.10'))

    def test_prices_shown(self):
        for name, legs in (('Home & Over 2.5', ((HOME, D('2.10')), (OVER, D('1.90')))),
                           ('Draw & Under 2.5', ((DRAW, D('3.40')), (UNDER, D('1.90')))),
                           ('Home & BTTS yes', ((HOME, D('2.10')), (GG, D('1.80')))),
                           ('Home & BTTS no', ((HOME, D('2.10')), (NG, D('2.00')))),
                           ('BTTS yes & Over 2.5', ((GG, D('1.80')), (OVER, D('1.90'))))):
            print(f'{name:22} product {legs[0][1] * legs[1][1]:.2f} -> {self.price(*legs)}')
