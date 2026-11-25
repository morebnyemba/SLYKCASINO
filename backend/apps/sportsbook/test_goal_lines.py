"""Goal lines stop at 4.5: over/under 5.5 and up are never offered."""
from decimal import Decimal as D

from django.test import TestCase
from rest_framework.test import APIClient

from apps.sportsbook import services as sb
from apps.sportsbook.market_feed import FeedMarketData, FeedOutcome
from apps.sportsbook.models import Event, Market
from apps.sportsbook.test_markets import _market, _outcome, _player


def ou(line: str) -> FeedMarketData:
    return FeedMarketData(key=f'over_under:ft:{line}', name=f'Over/Under {line}', group='goals', kind='over_under',
                          period='ft', line=D(line), sort_order=0,
                          outcomes=(FeedOutcome('over', f'Over {line}', D('1.90')), FeedOutcome('under', f'Under {line}', D('1.90'))))


class GoalLineCapTests(TestCase):
    def setUp(self):
        self.event = Event.objects.create(name='Chelsea v Arsenal', odds=D('2.00'), odds_draw=D('3.30'), odds_away=D('3.60'),
                                          is_open=True)

    def test_the_feed_never_offers_lines_above_4_5(self):
        old = _market(self.event, 'over_under', 'over_under:ft:6.5', [('over', '9.00'), ('under', '1.02')], line=D('6.5'))
        sb.apply_feed_markets(self.event, [ou(x) for x in ('0.5', '1.5', '2.5', '3.5', '4.5', '5.5', '6.5')])
        lines = sorted(Market.objects.filter(event=self.event, is_open=True).values_list('line', flat=True))
        self.assertEqual(lines, [D('0.5'), D('1.5'), D('2.5'), D('3.5'), D('4.5')])
        self.assertFalse(Market.objects.filter(event=self.event, line=D('5.5')).exists())    # never created
        old.refresh_from_db()
        self.assertFalse(old.is_open)                                                        # already there: closed

    def test_hidden_from_the_match_page_and_refused_at_placement(self):
        _market(self.event, 'over_under', 'over_under:ft:4.5', [('over', '4.00'), ('under', '1.20')], line=D('4.5'))
        big = _market(self.event, 'over_under', 'over_under:ft:5.5', [('over', '8.00'), ('under', '1.05')], line=D('5.5'))
        data = APIClient().get(f'/api/events/{self.event.id}/').json()
        self.assertEqual([m['line'] for m in data['markets']], ['4.50'])
        player = _player('linecap')
        with self.assertRaisesMessage(ValueError, 'suspended'):
            o = _outcome(big, 'under')
            sb.place_bet(event='x', stake=D('5'), odds=o.odds, player_id=player.id, event_id=self.event.id,
                         outcome_id=o.id, wallet='deposit')
