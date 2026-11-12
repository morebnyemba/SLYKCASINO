"""Staff reverse a ticket settled as won by mistake: the winnings come back,
never more than was paid, never below zero, once, and on the record."""
from __future__ import annotations

from decimal import Decimal as D

from django.contrib.auth.models import User
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts import services as accounts
from apps.accounts.models import AuditLog
from apps.revenue import services as revenue
from apps.risk import services as risk
from apps.sportsbook import reversal
from apps.sportsbook import services as sb
from apps.sportsbook.models import Bet, BetLeg, BetSlip, TicketReversal
from apps.wallet import services as wallet
from apps.wallet.models import LedgerEntry


class Base(TestCase):
    def setUp(self):
        self.player = accounts.create_player(username='lucky')
        wallet.credit(player_id=self.player.id, amount=D('100'), kind='deposit', idempotency_key='r:d')
        self.boss = APIClient()
        self.boss.force_authenticate(User.objects.create_superuser('boss', 'b@example.com', 'x'))

    def bal(self):
        return {k: str(v) for k, v in wallet.get_balances(self.player.id).items()}

    def won_single(self, stake='10', odds='3.00', bucket='deposit'):
        bet = sb.place_bet(wallet=bucket, event='A v B', stake=D(stake), odds=D(odds), player_id=self.player.id)
        return sb.settle_bet(bet.id, 'won')


class SingleTests(Base):
    def test_lost_takes_back_stake_and_winnings(self):
        bet = self.won_single()                                     # paid 30: 10 stake back to Deposit, 20 to Winnings
        self.assertEqual(self.bal(), {'deposit': '100.00', 'bonus': '0.00', 'winnings': '20.00'})
        record = reversal.reverse('single', bet.id, outcome='lost', reason='Wrong result entered', by='boss')
        self.assertEqual((record.owed, record.recovered, record.shortfall), (D('30.00'), D('30.00'), D('0.00')))
        self.assertEqual(self.bal(), {'deposit': '90.00', 'bonus': '0.00', 'winnings': '0.00'})
        bet.refresh_from_db()
        self.assertEqual((bet.status, bet.payout), ('lost', D('0.00')))
        self.assertEqual(LedgerEntry.objects.filter(kind='bet_reversal').count(), 2)
        self.assertTrue(AuditLog.objects.filter(event_type='ticket_reversed', player_id=self.player.id).exists())

    def test_void_takes_back_only_the_winnings(self):
        bet = self.won_single()
        record = reversal.reverse('single', bet.id, outcome='void', reason='Match abandoned', by='boss')
        self.assertEqual(record.owed, D('20.00'))
        self.assertEqual(self.bal(), {'deposit': '100.00', 'bonus': '0.00', 'winnings': '0.00'})
        bet.refresh_from_db()
        self.assertEqual(bet.status, 'void')

    def test_only_won_tickets_and_only_once(self):
        open_bet = sb.place_bet(wallet='deposit', event='x', stake=D('5'), odds=D('2'), player_id=self.player.id)
        with self.assertRaisesMessage(reversal.ReversalError, 'settled as won'):
            reversal.reverse('single', open_bet.id, outcome='lost', reason='because reasons', by='boss')
        bet = self.won_single()
        reversal.reverse('single', bet.id, outcome='lost', reason='Wrong result entered', by='boss')
        with self.assertRaises(reversal.ReversalError):
            reversal.reverse('single', bet.id, outcome='lost', reason='Wrong result entered', by='boss')
        self.assertEqual(TicketReversal.objects.count(), 1)

    def test_a_reason_is_required(self):
        bet = self.won_single()
        with self.assertRaisesMessage(reversal.ReversalError, 'Say why'):
            reversal.reverse('single', bet.id, outcome='lost', reason=' ', by='boss')

    def test_money_already_spent_is_refused_unless_accepted_then_recorded_as_owed(self):
        bet = self.won_single()
        wallet.debit(player_id=self.player.id, amount=D('20'), kind='bet_stake', bucket='winnings', idempotency_key='spent')
        wallet.debit(player_id=self.player.id, amount=D('95'), kind='bet_stake', bucket='deposit', idempotency_key='spent2')
        with self.assertRaisesMessage(reversal.ReversalError, 'only holds $5.00 of the $30.00'):
            reversal.reverse('single', bet.id, outcome='lost', reason='Wrong result entered', by='boss')
        self.assertEqual(Bet.objects.get(pk=bet.id).status, 'won')                    # nothing changed
        record = reversal.reverse('single', bet.id, outcome='lost', reason='Wrong result entered', by='boss',
                                  accept_shortfall=True, freeze_withdrawals=True)
        self.assertEqual((record.recovered, record.shortfall), (D('5.00'), D('25.00')))
        self.assertEqual(self.bal(), {'deposit': '0.00', 'bonus': '0.00', 'winnings': '0.00'})   # never negative
        self.assertTrue(risk.profile(self.player.id).withdrawals_frozen)

    def test_winnings_moved_between_cash_wallets_are_still_recovered(self):
        bet = self.won_single()
        wallet.debit(player_id=self.player.id, amount=D('20'), kind='bet_stake', bucket='winnings', idempotency_key='spent')
        record = reversal.reverse('single', bet.id, outcome='lost', reason='Wrong result entered', by='boss')
        self.assertEqual(record.shortfall, D('0.00'))               # the missing 20 came from Deposit
        self.assertEqual(self.bal()['deposit'], '70.00')

    def test_reports_count_the_reversal_against_wins(self):
        from django.utils import timezone
        bet = self.won_single()
        day = timezone.localdate()
        self.assertEqual(revenue.day_ggr(day), D('-20.00'))         # 10 staked, 30 paid
        reversal.reverse('single', bet.id, outcome='lost', reason='Wrong result entered', by='boss')
        self.assertEqual(revenue.day_ggr(day), D('10.00'))          # the stake is kept, nothing paid
        kpis = wallet.ledger_kpis(None, None, timezone.now())
        self.assertEqual((kpis['wins'], kpis['ggr']), ('0.00', '10.00'))


class MultipleAndBonusTests(Base):
    def won_slip(self, bucket='deposit', stake='10'):
        slip = sb.place_accumulator(stake=D(stake), player_id=self.player.id, wallet=bucket,
                                    legs=[{'event': f'M{i}', 'odds': D('2.00')} for i in range(10)])
        BetLeg.objects.filter(slip=slip).update(result='won')
        return sb._settle_slip_if_ready(slip.id)

    def test_a_multiple_gives_back_its_payout_and_its_multibet_bonus(self):
        from apps.sportsbook.models import MultiBetBonusTier
        MultiBetBonusTier.objects.update_or_create(min_legs=5, defaults={'percent': D('10'), 'is_active': True})
        slip = self.won_slip(stake='1')                             # 1 x 1024
        self.assertGreater(slip.bonus, 0)
        before = self.bal()
        record = reversal.reverse('multiple', slip.id, outcome='lost', reason='Leg settled wrongly', by='boss')
        self.assertEqual(record.owed, D('1024.00') + slip.bonus)
        self.assertEqual(self.bal(), {'deposit': '99.00', 'bonus': '0.00', 'winnings': '0.00'}, before)
        slip.refresh_from_db()
        self.assertEqual((slip.status, slip.payout, slip.bonus), ('lost', D('0.00'), D('0.00')))

    def test_a_bonus_ticket_comes_back_out_of_the_bonus_wallet(self):
        wallet.credit(player_id=self.player.id, amount=D('5'), kind='bonus', idempotency_key='r:b')
        slip = self.won_slip(bucket='bonus', stake='5')
        self.assertEqual(self.bal()['bonus'], '5120.00')
        reversal.reverse('multiple', slip.id, outcome='lost', reason='Leg settled wrongly', by='boss')
        self.assertEqual(self.bal(), {'deposit': '100.00', 'bonus': '0.00', 'winnings': '0.00'})
        from apps.wallet import bonus
        self.assertEqual(bonus.progress(self.player.id)['wins'], 0)


class ApiTests(Base):
    def test_dry_run_then_reverse_superuser_only(self):
        bet = self.won_single()
        url = f'/api/admin/tickets/S{bet.id}/reverse/'
        staff = APIClient()
        staff.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))
        self.assertEqual(staff.post(url, {'outcome': 'lost', 'reason': 'Wrong result'}, format='json').status_code, 403)
        detail = self.boss.get(f'/api/admin/tickets/S{bet.id}/').json()
        self.assertEqual((detail['can_reverse'], detail['reversal']), (True, None))
        dry = self.boss.post(url, {'outcome': 'lost', 'dry_run': True}, format='json').json()
        self.assertEqual((dry['owed'], dry['recovered'], dry['shortfall']), ('30.00', '30.00', '0.00'))
        self.assertEqual(Bet.objects.get(pk=bet.id).status, 'won')
        res = self.boss.post(url, {'outcome': 'lost', 'reason': 'Wrong result entered'}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        detail = self.boss.get(f'/api/admin/tickets/S{bet.id}/').json()
        self.assertEqual((detail['can_reverse'], detail['reversal']['recovered']), (False, '30.00'))
        self.assertEqual(self.boss.post(url, {'outcome': 'lost', 'reason': 'Wrong result entered'}, format='json').status_code, 400)
