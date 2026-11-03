"""The three wallets: Deposit, Bonus and Winnings never mix, and only
Winnings can leave the platform. These run with the real minimum odds."""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction
from django.test import TestCase
from rest_framework.test import APIClient

from apps.accounts import services as account_services
from apps.accounts.models import AuditLog
from apps.jet import services as jet_services
from apps.sportsbook import services as sb
from apps.wallet import services, withdrawals
from apps.wallet.models import LedgerEntry, PaymentTransaction, Wallet, WithdrawalSettings
from apps.wallet.recovery import reconcile_wallet_ledger

D = Decimal
pytestmark = pytest.mark.wallet_rules
ECOCASH = {'method': 'ecocash', 'account_number': '0771234567'}


def balances(player):
    return {k: str(v) for k, v in services.get_balances(player.id).items()}


class Base(TestCase):
    def setUp(self):
        self.player = account_services.create_player(username='tatenda')
        self.player.kyc_status = self.player.Kyc.VERIFIED
        self.user = User.objects.create(username='tatenda')
        self.player.user = self.user
        self.player.save(update_fields=['kyc_status', 'user'])
        services.deposit(player_id=self.player.id, amount=D('100'), idempotency_key='dep:1')
        services.credit(player_id=self.player.id, amount=D('50'), kind='bonus', idempotency_key='bonus:1')
        self.api = APIClient()
        self.api.force_authenticate(self.user)


class SeparationTests(Base):
    def test_money_lands_in_its_own_wallet(self):
        self.assertEqual(balances(self.player), {'deposit': '100.00', 'bonus': '50.00', 'winnings': '0.00'})
        body = self.api.get('/api/wallet/').json()
        self.assertEqual(body['wallets']['deposit']['min_odds'], '1.50')
        self.assertEqual(body['wallets']['bonus']['min_odds'], '10.00')
        self.assertEqual((body['balance'], body['withdrawable']), ('150.00', '0.00'))

    def test_a_bet_needs_a_chosen_wallet_and_its_minimum_odds(self):
        bet = dict(event='A v B', stake=D('10'), player_id=self.player.id)
        with self.assertRaisesMessage(services.WalletRuleError, 'Choose which wallet'):
            sb.place_bet(odds=D('6'), **bet)
        with self.assertRaisesMessage(services.WalletRuleError, 'at least 1.50'):
            sb.place_bet(odds=D('1.49'), wallet='deposit', **bet)
        with self.assertRaisesMessage(services.WalletRuleError, 'at least 10.00'):
            sb.place_bet(odds=D('9.50'), wallet='bonus', **bet)
        with self.assertRaisesMessage(services.WalletRuleError, 'multiple of at least 10'):
            sb.place_bet(odds=D('12'), wallet='bonus', **bet)   # bonus money: 10-leg multiples only
        sb.place_bet(odds=D('5'), wallet='deposit', **bet)
        self.assertEqual(balances(self.player), {'deposit': '90.00', 'bonus': '50.00', 'winnings': '0.00'})

    def test_never_takes_from_a_wallet_the_player_did_not_choose(self):
        # 100 in Deposit, nothing in Winnings: a Winnings bet is refused, not topped up.
        with self.assertRaises(services.InsufficientFunds):
            sb.place_bet(event='A v B', stake=D('10'), odds=D('2'), player_id=self.player.id, wallet='winnings')
        self.assertEqual(balances(self.player), {'deposit': '100.00', 'bonus': '50.00', 'winnings': '0.00'})

    def test_minimum_odds_apply_to_the_combined_odds_of_a_multiple(self):
        legs = [{'event': 'A', 'odds': D('1.2')}, {'event': 'B', 'odds': D('1.2')}]
        with self.assertRaisesMessage(services.WalletRuleError, 'at least 1.50'):
            sb.place_accumulator(stake=D('10'), legs=legs, player_id=self.player.id, wallet='deposit')
        legs.append({'event': 'C', 'odds': D('1.5')})
        slip = sb.place_accumulator(stake=D('10'), legs=legs, player_id=self.player.id, wallet='deposit')
        self.assertEqual((slip.combined_odds, slip.wallet), (D('2.16'), 'deposit'))

    def test_api_refuses_a_bet_without_a_wallet(self):
        res = self.api.post('/api/bets/', {'event': 'A v B', 'stake': '5', 'odds': '6'}, format='json')
        self.assertEqual(res.status_code, 400)
        res = self.api.post('/api/bets/', {'event': 'A v B', 'stake': '5', 'odds': '6', 'wallet': 'deposit'}, format='json')
        self.assertEqual((res.status_code, res.json()['wallet']), (201, 'deposit'))


class PayoutTests(Base):
    def test_stake_returns_to_its_wallet_and_only_profit_is_winnings(self):
        dep = sb.place_bet(event='A v B', stake=D('10'), odds=D('5'), player_id=self.player.id, wallet='deposit')
        sb.settle_bet(dep.id, 'won')   # pays 50: 10 back to Deposit, 40 to Winnings
        self.assertEqual(balances(self.player), {'deposit': '100.00', 'bonus': '50.00', 'winnings': '40.00'})
        # (Bonus tickets pay back into the Bonus wallet: see test_bonus_rules.)

    def test_void_refunds_the_source_wallet_and_a_loss_pays_nothing(self):
        services.credit(player_id=self.player.id, amount=D('10'), kind='adjustment', bucket='winnings', idempotency_key='w')
        void = sb.place_bet(event='A v B', stake=D('10'), odds=D('11'), player_id=self.player.id, wallet='winnings')
        lost = sb.place_bet(event='C v D', stake=D('10'), odds=D('6'), player_id=self.player.id, wallet='deposit')
        sb.settle_bet(void.id, 'void')
        sb.settle_bet(lost.id, 'lost')
        self.assertEqual(balances(self.player), {'deposit': '90.00', 'bonus': '50.00', 'winnings': '10.00'})

    def test_cashing_out_cannot_turn_a_deposit_into_winnings(self):
        from apps.sportsbook.cashout import cash_out
        from apps.sportsbook.models import Event
        ev = Event.objects.create(name='E v F', odds=D('6'), odds_draw=D('4'), odds_away=D('1.5'), is_open=True)
        bet = sb.place_bet(event='E v F', stake=D('10'), odds=D('6'), player_id=self.player.id,
                           wallet='deposit', event_id=ev.id, selection='home')
        from apps.sportsbook import cashout
        offer = cashout.bet_offer(bet, cashout.CashoutSettings.load())
        if not offer.available:
            self.skipTest(f'no cash-out offer: {offer.reason}')
        cash_out(kind='bet', ticket_id=bet.id, player_id=self.player.id, expected=offer.value)
        b = services.get_balances(self.player.id)
        # Whatever the offer, at most the stake goes back to Deposit and only
        # a profit over the stake reaches Winnings.
        self.assertEqual(b['deposit'] + b['winnings'], D('90') + offer.value)
        self.assertEqual(b['winnings'], max(offer.value - D('10'), D('0')))

    def test_aviator_low_cash_out_cannot_launder_a_deposit(self):
        """Cashing out at 1.01x pays 10.10: the 10 goes back to Deposit and only
        0.10 reaches Winnings — not the whole 10.10."""
        from datetime import timedelta

        from django.utils import timezone

        from apps.jet import engine
        from apps.jet.models import JetRound
        now = timezone.now()
        rnd = jet_services.open_round(now=now)
        JetRound.objects.filter(pk=rnd.pk).update(crash_point=D('5.00'))
        rnd.refresh_from_db()
        bet = jet_services.place_bet(player=self.player, stake='10', wallet='deposit', now=now)
        jet_services.start_flight(rnd.id, now=rnd.betting_ends_at)
        at = rnd.betting_ends_at + timedelta(seconds=engine.seconds_to(D('1.01')) + 0.01)
        bet = jet_services.cash_out(player_id=self.player.id, bet_id=bet.id, now=at)
        self.assertEqual(bet.payout, D('10.10'))
        self.assertEqual(balances(self.player), {'deposit': '100.00', 'bonus': '50.00', 'winnings': '0.10'})


class WithdrawalTests(Base):
    def test_only_winnings_can_be_withdrawn(self):
        res = self.api.post('/api/wallet/withdraw/', {'wallet': 'winnings', 'amount': '10', **ECOCASH}, format='json')
        self.assertEqual((res.status_code, res.json()['withdrawable']), (402, '0.00'))

    def test_asking_for_bonus_money_is_refused_and_flagged(self):
        res = self.api.post('/api/wallet/withdraw/', {'amount': '10', 'wallet': 'bonus', **ECOCASH}, format='json')
        self.assertEqual(res.status_code, 403)
        flagged = AuditLog.objects.filter(event_type='withdrawal_wallet_violation', player_id=self.player.id)
        self.assertEqual([f.metadata['wallet'] for f in flagged], ['bonus'])
        self.assertEqual(balances(self.player)['bonus'], '50.00')

    def test_the_player_must_choose_a_source(self):
        res = self.api.post('/api/wallet/withdraw/', {'amount': '10', **ECOCASH}, format='json')
        self.assertEqual(res.status_code, 400)
        self.assertIn('Choose the wallet', res.json()['detail'])

    def test_deposit_withdrawals_keep_a_50_percent_fee(self):
        WithdrawalSettings.objects.update_or_create(pk=1, defaults={'min_turnover_percent': 0})
        quote = self.api.post('/api/wallet/withdraw/quote/', {'amount': '40', 'wallet': 'deposit'}, format='json').json()
        self.assertEqual((quote['fee_percent'], quote['fee'], quote['payout_amount'], quote['available']),
                         ('50.00', '20.00', '20.00', '100.00'))
        res = self.api.post('/api/wallet/withdraw/', {'amount': '40', 'wallet': 'deposit', **ECOCASH}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        w = res.json()['withdrawal']
        self.assertEqual((w['wallet'], w['fee'], w['payout_amount']), ('deposit', '20.00', '20.00'))
        self.assertEqual(balances(self.player)['deposit'], '60.00')            # held from Deposit
        withdrawals.mark_paid(w['id'], reference='MP-9', confirm_amount='20')
        entries = {e.kind: (e.bucket, e.amount) for e in LedgerEntry.objects.filter(
            reference__startswith=f"withdrawal:{w['id']}:", kind__in=('withdrawal', 'withdrawal_fee'))}
        self.assertEqual(entries, {'withdrawal': ('deposit', D('-20.00')), 'withdrawal_fee': ('deposit', D('-20.00'))})
        self.assertEqual(balances(self.player), {'deposit': '60.00', 'bonus': '50.00', 'winnings': '0.00'})
        staff = APIClient()
        staff.force_authenticate(User.objects.create_user('cashier', 'c@example.com', 'x', is_staff=True))
        rows = staff.get('/api/admin/withdrawals/', {'status': 'all', 'wallet': 'deposit'}).json()['results']
        self.assertEqual([(r['id'], r['wallet'], r['fee']) for r in rows], [(w['id'], 'deposit', '20.00')])
        self.assertEqual(staff.get('/api/admin/withdrawals/', {'status': 'all', 'wallet': 'winnings'}).json()['results'], [])

    def test_minimum_withdrawal_is_one_dollar(self):
        WithdrawalSettings.objects.all().delete()
        self.assertEqual(WithdrawalSettings.load().min_amount, D('1.00'))

    def test_five_percent_fee_is_kept_and_recorded(self):
        services.credit(player_id=self.player.id, amount=D('100'), kind='adjustment', bucket='winnings', idempotency_key='w')
        WithdrawalSettings.objects.update_or_create(pk=1, defaults={'min_turnover_percent': 0})
        res = self.api.post('/api/wallet/withdraw/', {'amount': '100', 'wallet': 'winnings', **ECOCASH}, format='json')
        self.assertEqual(res.status_code, 201, res.content)
        w = res.json()['withdrawal']
        self.assertEqual((w['amount'], w['fee'], w['payout_amount']), ('100.00', '5.00', '95.00'))
        with self.assertRaises(withdrawals.WithdrawalError):  # staff confirm what they sent, not the gross
            withdrawals.mark_paid(w['id'], reference='MP-1', confirm_amount='100')
        withdrawals.mark_paid(w['id'], reference='MP-1', confirm_amount='95')
        entries = {e.kind: e.amount for e in LedgerEntry.objects.filter(reference__startswith=f"withdrawal:{w['id']}:")
                   if e.kind in ('withdrawal', 'withdrawal_fee')}
        self.assertEqual(entries, {'withdrawal': D('-95.00'), 'withdrawal_fee': D('-5.00')})
        self.assertEqual(balances(self.player)['winnings'], '0.00')


class DatabaseRuleTests(Base):
    def test_ledger_rows_cannot_be_changed_or_deleted(self):
        from django.db import connection
        if connection.vendor != 'postgresql':
            self.skipTest('the append-only trigger is Postgres-only')
        from django.db import DatabaseError
        entry = LedgerEntry.objects.filter(wallet__player_id=self.player.id).first()
        with self.assertRaises(DatabaseError), transaction.atomic():
            LedgerEntry.objects.filter(pk=entry.pk).update(amount=D('999'))
        with self.assertRaises(DatabaseError), transaction.atomic():
            LedgerEntry.objects.filter(pk=entry.pk).delete()
        # Permanent account deletion is the one sanctioned exception.
        services.erase_player_data(self.player.id)
        self.assertFalse(LedgerEntry.objects.filter(wallet__player_id=self.player.id).exists())

    def test_a_deposit_can_only_ever_touch_the_deposit_wallet(self):
        with self.assertRaises(ValueError):
            services.credit(player_id=self.player.id, amount=D('5'), kind='deposit', bucket='winnings', idempotency_key='x')
        with self.assertRaises(ValueError):
            services.credit(player_id=self.player.id, amount=D('5'), kind='bonus', bucket='deposit', idempotency_key='y')
        wallet = Wallet.objects.get(player_id=self.player.id)
        for kind, bucket in (('deposit', 'winnings'), ('withdrawal', 'bonus'), ('withdrawal_fee', 'bonus'), ('bonus', 'winnings')):
            with self.assertRaises(IntegrityError), transaction.atomic():
                LedgerEntry.objects.create(wallet=wallet, idempotency_key=f'raw:{kind}', amount=D('-1'), kind=kind, bucket=bucket)

    def test_no_wallet_can_go_negative_or_drift_from_its_total(self):
        with self.assertRaises(IntegrityError), transaction.atomic():
            Wallet.objects.filter(player_id=self.player.id).update(deposit_balance=D('-1'), balance=D('49'))
        with self.assertRaises(IntegrityError), transaction.atomic():
            Wallet.objects.filter(player_id=self.player.id).update(winnings_balance=D('1000'))

    def test_every_entry_has_a_unique_reference(self):
        refs = [e.transaction_ref for e in LedgerEntry.objects.all()]
        self.assertEqual(len(refs), len(set(refs)))
        self.assertTrue(all(r.startswith('BB-') for r in refs))


class DepositRefundTests(Base):
    def setUp(self):
        super().setUp()
        PaymentTransaction.objects.create(reference='P1', player_id=self.player.id, method='ecocash',
                                          phone='0771234567', amount=D('100'), status='paid')
        self.staff = APIClient()
        self.staff.force_authenticate(User.objects.create_user('ops', 'o@example.com', 'x', is_staff=True))
        self.url = f'/api/admin/players/{self.player.id}/deposit-refund/'

    def refund(self, **kw):
        body = {'amount': '100', 'reason': 'self_exclusion', 'destination': '0771234567', 'reference': 'EC-9', **kw}
        return self.staff.post(self.url, body, format='json')

    def test_only_for_self_excluded_or_closed_accounts_and_only_to_the_source_number(self):
        self.assertIn('isn’t self-excluded', self.refund().json()['detail'])
        self.player.self_excluded = True
        self.player.save(update_fields=['self_excluded'])
        self.assertEqual(self.refund(destination='0779999999').status_code, 403)
        self.assertEqual(self.refund(amount='150').status_code, 400)
        res = self.refund()
        self.assertEqual(res.status_code, 201, res.content)
        self.assertEqual(balances(self.player)['deposit'], '0.00')
        self.assertTrue(AuditLog.objects.filter(event_type='deposit_refunded').exists())
        self.assertEqual(self.staff.get(self.url).json()['destinations'], ['0771234567'])

    def test_players_cannot_use_it(self):
        self.assertEqual(self.api.post(self.url, {}, format='json').status_code, 403)


class ReconcileTests(Base):
    def test_drift_in_one_wallet_is_repaired_and_reported(self):
        Wallet.objects.filter(player_id=self.player.id).update(deposit_balance=D('90'), bonus_balance=D('60'))
        report = reconcile_wallet_ledger()
        self.assertEqual(report.repaired, 1)
        self.assertEqual(balances(self.player), {'deposit': '100.00', 'bonus': '50.00', 'winnings': '0.00'})
        self.assertTrue(AuditLog.objects.filter(event_type='ledger_drift', player_id=self.player.id).exists())


class SplitMigrationTests(TestCase):
    def test_locked_bonus_goes_to_bonus_and_the_rest_to_winnings(self):
        from importlib import import_module

        from django.apps import apps as global_apps

        from apps.promotions.models import Promotion, PromotionClaim
        player = account_services.create_player(username='veteran')
        wallet = services.ensure_wallet(player.id)
        for key, amount, kind in (('d', D('80'), 'deposit'), ('b', D('20'), 'bonus'), ('s', D('-30'), 'bet_stake')):
            LedgerEntry.objects.create(wallet=wallet, idempotency_key=f'old:{key}', amount=amount, kind=kind,
                                       bucket='winnings', legacy=True)
        promo = Promotion.objects.create(name='Welcome', code='w', bonus_amount=D('20'))
        PromotionClaim.objects.create(player_id=player.id, promotion=promo, bonus_amount=D('20'),
                                      wagering_required=D('100'), wagering_progress=D('30'), bonus_credited=True)
        from apps.wallet.testing import ledger_unlocked
        with ledger_unlocked():  # the split runs before the ledger is locked (0013)
            import_module('apps.wallet.migrations.0012_split_balances').split(global_apps, None)
        self.assertEqual(balances(player), {'deposit': '0.00', 'bonus': '20.00', 'winnings': '50.00'})
        reconcile_wallet_ledger()  # the ledger agrees with the split
        self.assertFalse(AuditLog.objects.filter(event_type='ledger_drift', player_id=player.id).exists())
