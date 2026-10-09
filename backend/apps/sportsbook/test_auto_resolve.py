"""The settlement backstop: every market on a finished match ends up settled —
decided from the facts where possible, voided (refunded) where not — and
matches that never finish are voided."""
from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from unittest.mock import patch

from django.test import TestCase, override_settings
from django.utils import timezone

from apps.accounts import services as account_services
from apps.sportsbook import services as sb
from apps.sportsbook.market_feed import parse_markets
from apps.sportsbook.models import Bet, Event, Market, MarketOutcome
from apps.wallet import services as wallet_services

D = Decimal
BETS = [
    {'name': 'Goals Over/Under', 'values': [{'value': 'Over 2.5', 'odd': '1.90'}, {'value': 'Under 2.5', 'odd': '1.90'}]},
    {'name': 'Corners Over Under', 'values': [{'value': 'Over 9.5', 'odd': '1.90'}, {'value': 'Under 9.5', 'odd': '1.90'}]},
    {'name': 'Winning Margin', 'values': [{'value': 'Home by 1', 'odd': '3.00'}, {'value': 'Away by 1', 'odd': '4.00'}]},
]


@override_settings(SPORTSBOOK_AUTO_VOID_AFTER_HOURS=6, SPORTSBOOK_UNPLAYED_VOID_HOURS=72)
class AutoResolveTests(TestCase):
    def setUp(self):
        self.player = account_services.register_player(
            username='resolver', email='resolve@example.com', password='Passw0rd!', currency='USD',
        )
        wallet_services.credit(player_id=self.player.id, amount=D('100'), kind='deposit', idempotency_key='res:dep')

    def _event(self, hours_ago: float, **fields) -> Event:
        event = Event.objects.create(
            name='Home FC vs Away FC', odds=D('2.00'), odds_draw=D('3.40'), odds_away=D('3.80'),
            starts_at=timezone.now() - timedelta(hours=hours_ago), **fields,
        )
        sb.apply_feed_markets(event, parse_markets(BETS))
        return event

    def _before_kickoff(self, event, place):
        with patch('apps.sportsbook.services.timezone.now', return_value=event.starts_at - timedelta(hours=1)):
            return place()

    def _bet(self, event, market_kind, key, stake='10', metric='goals'):
        outcome = MarketOutcome.objects.filter(
            market__event=event, market__kind=market_kind, market__metric=metric, key=key,
        ).first()
        return self._before_kickoff(event, lambda: sb.place_bet(
            event='x', stake=D(stake), odds=outcome.odds, player_id=self.player.id, outcome_id=outcome.id,
        ))

    def _finish(self, event, home=2, away=1):
        Event.objects.filter(pk=event.pk).update(status='FT', score_home=home, score_away=away, is_open=False)

    def test_finished_match_settles_what_it_can_and_voids_the_rest(self):
        event = self._event(8)
        main = self._before_kickoff(event, lambda: sb.place_bet(
            event='x', stake=D('10'), odds=D('2.00'), player_id=self.player.id, event_id=event.id, selection='home'))
        goals = self._bet(event, 'over_under', 'over')          # 3 goals: won
        corners = self._bet(event, 'over_under', 'over', metric='corners')
        manual_key = MarketOutcome.objects.filter(market__event=event, market__kind=Market.Kind.MANUAL).first().key
        manual = self._bet(event, Market.Kind.MANUAL, manual_key, metric=Market.objects.get(
            event=event, kind=Market.Kind.MANUAL).metric)
        self._finish(event)

        report = sb.auto_resolve_markets()

        self.assertEqual(report['finished_events'], 1)
        self.assertFalse(Market.objects.filter(event=event, settled=False).exists())
        statuses = {b.id: b.status for b in Bet.objects.filter(pk__in=[main.id, goals.id, corners.id, manual.id])}
        self.assertEqual(statuses[main.id], Bet.Status.WON)
        self.assertEqual(statuses[goals.id], Bet.Status.WON)
        self.assertEqual(statuses[corners.id], Bet.Status.VOID)   # corner count never published
        self.assertEqual(statuses[manual.id], Bet.Status.VOID)    # bet type not readable from the facts
        self.assertGreaterEqual(report['markets_voided'], 2)

        # Idempotent: a second run changes nothing and refunds nothing twice.
        balance = wallet_services.get_balance_dto(self.player.id).balance
        self.assertEqual(sb.auto_resolve_markets()['finished_events'], 0)
        self.assertEqual(wallet_services.get_balance_dto(self.player.id).balance, balance)

    def test_operators_get_a_grace_period_first(self):
        event = self._event(3)
        manual = Market.objects.get(event=event, kind=Market.Kind.MANUAL)
        bet = self._bet(event, Market.Kind.MANUAL, manual.outcomes.first().key, metric=manual.metric)
        self._finish(event)
        self.assertEqual(sb.auto_resolve_markets()['markets_voided'], 0)
        bet.refresh_from_db()
        self.assertEqual(bet.status, Bet.Status.OPEN)

    def test_match_that_never_finished_is_voided(self):
        stale = self._event(80, status='PST')
        bet = self._bet(stale, 'over_under', 'over')
        recent = self._event(30, status='PST')
        recent_bet = self._bet(recent, 'over_under', 'over')
        before = wallet_services.get_balance_dto(self.player.id).balance

        report = sb.auto_resolve_markets()

        self.assertEqual(report['unplayed_voided'], 1)
        bet.refresh_from_db(); recent_bet.refresh_from_db()
        self.assertEqual(bet.status, Bet.Status.VOID)
        self.assertEqual(recent_bet.status, Bet.Status.OPEN)
        self.assertEqual(wallet_services.get_balance_dto(self.player.id).balance, before + D('10'))
        self.assertFalse(Market.objects.filter(event=stale, settled=False).exists())

    @override_settings(SPORTSBOOK_AUTO_VOID_AFTER_HOURS=0, SPORTSBOOK_UNPLAYED_VOID_HOURS=0)
    def test_both_steps_can_be_switched_off(self):
        event = self._event(80)
        self._finish(event)
        self.assertEqual(sb.auto_resolve_markets(), {
            'finished_events': 0, 'markets_settled': 0, 'markets_voided': 0, 'unplayed_voided': 0,
        })
