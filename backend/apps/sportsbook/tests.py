"""sportsbook tests — event listing, bet placement, settlement."""
from __future__ import annotations

from decimal import Decimal

from django.test import TestCase
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.accounts import services as account_services
from apps.sportsbook import services as sportsbook_services
from apps.sportsbook.models import Bet, Event
from apps.wallet import services as wallet_services


def _make_player(username='sbplayer', email='sb@example.com'):
    player = account_services.register_player(
        username=username, email=email, password='Passw0rd!', currency='USD',
    )
    wallet_services.credit(
        player_id=player.id, amount=Decimal('1000.00'),
        kind='deposit', idempotency_key=f'setup:sb:{player.id}',
    )
    return player


def _make_event(name='Test Match', odds=Decimal('2.00')):
    return Event.objects.create(name=name, odds=odds, is_open=True)


class EventListTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        _make_event('Event One')
        _make_event('Event Two')

    def test_event_list_public(self):
        resp = self.client.get('/api/events/')
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(resp.data), 2)


class BetPlacementTests(TestCase):
    def setUp(self):
        self.player = _make_player()
        self.event = _make_event()
        refresh = RefreshToken.for_user(self.player.user)
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f'Bearer {str(refresh.access_token)}')

    def test_bet_requires_auth(self):
        anon_client = APIClient()
        resp = anon_client.post('/api/bets/', {
            'event': 'Test Match', 'stake': '10.00', 'odds': '2.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_place_bet_debits_wallet(self):
        before = wallet_services.get_balance(self.player.id)
        resp = self.client.post('/api/bets/', {
            'event': 'Test Match', 'stake': '50.00', 'odds': '2.00',
        }, format='json')
        self.assertEqual(resp.status_code, status.HTTP_201_CREATED)
        after = wallet_services.get_balance(self.player.id)
        self.assertEqual(before - after, Decimal('50.00'))

    def test_settle_bet_won_credits_wallet(self):
        bet = sportsbook_services.place_bet(
            event='Test Match', stake=Decimal('100.00'),
            odds=Decimal('2.00'), player_id=self.player.id,
        )
        before = wallet_services.get_balance(self.player.id)
        sportsbook_services.settle_bet(bet.id, 'won')
        after = wallet_services.get_balance(self.player.id)
        # Payout = 100 * 2.00 = 200
        self.assertEqual(after - before, Decimal('200.00'))

    def test_settle_bet_lost_no_credit(self):
        bet = sportsbook_services.place_bet(
            event='Test Match', stake=Decimal('50.00'),
            odds=Decimal('2.00'), player_id=self.player.id,
        )
        before = wallet_services.get_balance(self.player.id)
        sportsbook_services.settle_bet(bet.id, 'lost')
        after = wallet_services.get_balance(self.player.id)
        self.assertEqual(before, after)

    def test_settled_bet_has_correct_status(self):
        bet = sportsbook_services.place_bet(
            event='Test Match', stake=Decimal('10.00'),
            odds=Decimal('2.00'), player_id=self.player.id,
        )
        settled = sportsbook_services.settle_bet(bet.id, 'won')
        self.assertEqual(settled.status, Bet.Status.WON)


class SettleEventTests(TestCase):
    def setUp(self):
        self.player = _make_player(username='settler', email='settle@example.com')
        self.event = _make_event('Man Utd vs Arsenal')

    def _bet(self, selection, stake='50.00', odds='2.00'):
        return sportsbook_services.place_bet(
            event=f'Man Utd vs Arsenal — {selection}', stake=Decimal(stake), odds=Decimal(odds),
            player_id=self.player.id, event_id=self.event.id, selection=selection,
        )

    def test_settle_event_pays_matching_selection_only(self):
        home = self._bet('home')
        draw = self._bet('draw')
        away = self._bet('away')
        before = wallet_services.get_balance(self.player.id)

        count = sportsbook_services.settle_event(self.event.id, 'draw')

        self.assertEqual(count, 3)
        home.refresh_from_db(); draw.refresh_from_db(); away.refresh_from_db()
        self.assertEqual(draw.status, Bet.Status.WON)
        self.assertEqual(home.status, Bet.Status.LOST)
        self.assertEqual(away.status, Bet.Status.LOST)
        after = wallet_services.get_balance(self.player.id)
        # Only the 50.00 @ 2.00 draw bet pays out 100.00.
        self.assertEqual(after - before, Decimal('100.00'))

    def test_settle_event_void_refunds_all(self):
        self._bet('home'); self._bet('away')
        before = wallet_services.get_balance(self.player.id)
        sportsbook_services.settle_event(self.event.id, 'void')
        after = wallet_services.get_balance(self.player.id)
        # Two 50.00 stakes refunded.
        self.assertEqual(after - before, Decimal('100.00'))

    def test_settle_event_ignores_unlinked_bets(self):
        # A free-text bet with no event link must not be touched.
        sportsbook_services.place_bet(
            event='Some Other Match', stake=Decimal('20.00'), odds=Decimal('1.50'),
            player_id=self.player.id,
        )
        count = sportsbook_services.settle_event(self.event.id, 'home')
        self.assertEqual(count, 0)

    def test_settle_event_rejects_bad_result(self):
        with self.assertRaises(ValueError):
            sportsbook_services.settle_event(self.event.id, 'nonsense')
