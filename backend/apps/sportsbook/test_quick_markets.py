"""The match list's market chips: each event carries its O/U (nearest 2.5),
double chance and GG/NG prices, and the list stays a fixed number of queries."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal as D

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone
from rest_framework.test import APIClient

from apps.sportsbook.models import Event, Market, MarketOutcome


def market(event, kind, outs, line=None, **kw):
    m = Market.objects.create(event=event, key=f'{kind}:{line}:{kw.get("period", "ft")}:{kw.get("metric", "goals")}',
                              name=kind, kind=kind, line=line, **kw)
    for i, (key, odds) in enumerate(outs):
        MarketOutcome.objects.create(market=m, key=key, label=key.title(), odds=D(odds), sort_order=i)
    return m


class QuickMarketsTests(TestCase):
    def setUp(self):
        self.ev = Event.objects.create(name='A vs B', odds=D('2.0'), odds_draw=D('3.2'), odds_away=D('3.5'),
                                       starts_at=timezone.now() + timedelta(hours=3))

    def rows(self):
        res = APIClient().get('/api/events/?upcoming=true&page_size=50')
        self.assertEqual(res.status_code, 200)
        return {r['id']: r for r in res.json()['results']}

    def test_lists_ou_nearest_two_and_a_half_dc_and_gg(self):
        market(self.ev, 'over_under', [('over', '1.3'), ('under', '3.4')], D('1.5'))
        market(self.ev, 'over_under', [('over', '1.9'), ('under', '1.9')], D('2.5'))
        market(self.ev, 'double_chance', [('x2', '1.6'), ('1x', '1.3'), ('12', '1.25')])
        market(self.ev, 'btts', [('yes', '1.8'), ('no', '2.0')])
        q = self.rows()[self.ev.id]['quick_markets']
        self.assertEqual(q['ou']['line'], '2.5')
        self.assertEqual([o['key'] for o in q['ou']['outcomes']], ['over', 'under'])
        self.assertEqual([o['key'] for o in q['dc']['outcomes']], ['1x', '12', 'x2'])  # column order, not feed order
        self.assertEqual(q['gg']['outcomes'][0]['odds'], '1.80')

    def test_falls_back_to_nearest_line_and_skips_incomplete_or_wrong_markets(self):
        market(self.ev, 'over_under', [('over', '1.5'), ('under', '2.4')], D('3.5'))
        market(self.ev, 'btts', [('yes', '1.8')])                                    # "No" missing
        market(self.ev, 'over_under', [('over', '1.9'), ('under', '1.9')], D('2.5'), period='1h')  # first half
        market(self.ev, 'over_under', [('over', '1.9'), ('under', '1.9')], D('2.5'), metric='corners')
        closed = market(self.ev, 'double_chance', [('1x', '1.3'), ('12', '1.2'), ('x2', '1.6')])
        closed.is_open = False
        closed.save()
        q = self.rows()[self.ev.id]['quick_markets']
        self.assertEqual(q['ou']['line'], '3.5')
        self.assertNotIn('gg', q)
        self.assertNotIn('dc', q)

    def test_query_count_does_not_grow_with_events(self):
        for n in range(6):
            ev = Event.objects.create(name=f'C{n} vs D{n}', odds=D('2'), starts_at=timezone.now() + timedelta(hours=4))
            market(ev, 'btts', [('yes', '1.8'), ('no', '2.0')])
        self.rows()  # warm caches (settings, rules)
        with CaptureQueriesContext(connection) as small:
            self.rows()
        for n in range(6, 20):
            ev = Event.objects.create(name=f'C{n} vs D{n}', odds=D('2'), starts_at=timezone.now() + timedelta(hours=4))
            market(ev, 'btts', [('yes', '1.8'), ('no', '2.0')])
        with CaptureQueriesContext(connection) as big:
            self.rows()
        self.assertLessEqual(len(big), len(small) + 2)

    def test_event_page_unaffected(self):
        res = APIClient().get(f'/api/events/{self.ev.id}/')
        self.assertEqual(res.status_code, 200)
        self.assertIsNone(res.json()['quick_markets'])
        self.assertIn('markets', res.json())
