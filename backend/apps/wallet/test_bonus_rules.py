"""The Bonus wallet's rules (wallet.bonus), with the real defaults: sportsbook
only, the whole wallet on one 10+ selection multiple at 1.50+ each, winnings
back into Bonus, and two wins in a row to unlock up to $500 into Winnings."""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import TestCase

from apps.accounts import services as account_services
from apps.sportsbook import services as sb
from apps.sportsbook.models import BetSlip
from apps.wallet import bonus, services
from apps.wallet.models import BonusRollover, LedgerEntry

D = Decimal
pytestmark = pytest.mark.wallet_rules


def legs(n=10, odds='1.50'):
    return [{'event': f'Match {i}', 'odds': D(odds)} for i in range(n)]


class BonusRuleTests(TestCase):
    def setUp(self):
        self.player = account_services.create_player(username='bonus_player')
        services.ensure_wallet(self.player.id)
        services.credit(player_id=self.player.id, amount=D('10'), kind='bonus', idempotency_key='b1')
        services.credit(player_id=self.player.id, amount=D('50'), kind='deposit', idempotency_key='d1')

    def bal(self):
        return {k: str(v) for k, v in services.get_balances(self.player.id).items()}

    def place(self, *, n=10, odds='1.50', stake=None):
        stake = stake if stake is not None else services.get_balances(self.player.id)['bonus']
        return sb.place_accumulator(stake=D(stake), legs=legs(n, odds), player_id=self.player.id, wallet='bonus')

    def win(self, slip):
        for leg in slip.legs.all():
            leg.result = 'won'
            leg.save(update_fields=['result'])
        return sb._settle_slip_if_ready(slip.id)

    def lose(self, slip):
        leg = slip.legs.first()
        leg.result = 'lost'
        leg.save(update_fields=['result'])
        return sb._settle_slip_if_ready(slip.id)

    def test_ticket_shape_and_full_stake(self):
        with self.assertRaisesMessage(services.WalletRuleError, 'at least 10 selections'):
            self.place(n=9, odds='2')
        with self.assertRaisesMessage(services.WalletRuleError, 'odds of at least 1.50'):
            sb.place_accumulator(stake=D('10'), legs=[*legs(9), {'event': 'X', 'odds': D('1.40')}],
                                 player_id=self.player.id, wallet='bonus')
        with self.assertRaisesMessage(services.WalletRuleError, 'whole Bonus wallet: $10.00'):
            self.place(stake='5')
        with self.assertRaisesMessage(services.WalletRuleError, 'multiple of at least 10'):
            sb.place_bet(event='A', stake=D('10'), odds=D('60'), player_id=self.player.id, wallet='bonus')
        slip = self.place()
        self.assertEqual(slip.wallet, 'bonus')
        self.assertEqual(self.bal()['bonus'], '0.00')

    def test_not_for_aviator_or_casino(self):
        from apps.casino import services as casino
        from apps.jet import services as jet
        with self.assertRaisesMessage(services.WalletRuleError, 'only be used on sports'):
            casino.place_crash_bet(player_id=self.player.id, stake=D('10'), wallet='bonus')
        with self.assertRaisesMessage(jet.JetError, 'only be used on sports'):
            jet.place_bet(player=self.player, stake='10', wallet='bonus')

    def test_winnings_stay_in_bonus_until_two_wins_in_a_row_then_unlock_up_to_the_cap(self):
        first = self.win(self.place())          # 10 x 1.5^10 = 576.65
        self.assertEqual(first.status, BetSlip.Status.WON)
        self.assertEqual(self.bal(), {'deposit': '50.00', 'bonus': '576.65', 'winnings': '0.00'})
        self.assertEqual(bonus.progress(self.player.id)['wins'], 1)
        self.win(self.place())                  # 576.65 x 57.67 → into Bonus, then converts
        b = self.bal()
        self.assertEqual((b['bonus'], b['winnings']), ('0.00', '500.00'))   # capped at $500
        kinds = set(LedgerEntry.objects.filter(wallet__player_id=self.player.id).values_list('kind', flat=True))
        self.assertTrue({'bonus_conversion', 'bonus_forfeit'} <= kinds)
        self.assertEqual(bonus.progress(self.player.id)['wins'], 0)

    def test_a_loss_or_a_new_bonus_starts_the_count_again(self):
        self.win(self.place())
        self.assertEqual(BonusRollover.objects.get(player_id=self.player.id).wins, 1)
        services.credit(player_id=self.player.id, amount=D('5'), kind='bonus', idempotency_key='b2')
        self.assertEqual(BonusRollover.objects.get(player_id=self.player.id).wins, 0)
        self.lose(self.place())
        self.assertEqual(self.bal()['bonus'], '0.00')
        self.assertEqual(BonusRollover.objects.get(player_id=self.player.id).wins, 0)

    def test_bonus_tickets_cannot_be_cashed_out(self):
        from apps.sportsbook import cashout
        slip = self.place()
        self.assertEqual(cashout.slip_offer(slip).reason, 'Bonus bets can’t be cashed out.')

    def test_bonus_money_can_only_reach_winnings_through_a_conversion(self):
        from django.db import IntegrityError, transaction
        wallet = services.ensure_wallet(self.player.id)
        with self.assertRaises(IntegrityError), transaction.atomic():
            LedgerEntry.objects.create(wallet=wallet, idempotency_key='x', amount=D('5'), kind='bonus_conversion',
                                       bucket='bonus')
        with self.assertRaises(IntegrityError), transaction.atomic():
            LedgerEntry.objects.create(wallet=wallet, idempotency_key='y', amount=D('5'), kind='bonus_conversion',
                                       bucket='deposit')
