"""The Bonus wallet's rules (wallet.bonus), with the real defaults: sportsbook
only, the whole wallet on one 10+ selection multiple at 1.50+ each, winnings
back into Bonus, and two wins in a row to unlock into Winnings — up to $500, and
never more than 5× the bonus given."""
from __future__ import annotations

from decimal import Decimal

import pytest
from django.test import TestCase

from apps.accounts import services as account_services
from apps.sportsbook import services as sb
from apps.sportsbook.models import BetSlip
from apps.wallet import bonus, services
from apps.wallet.models import BonusRollover, LedgerEntry, WalletRules

D = Decimal
pytestmark = pytest.mark.wallet_rules


def legs(n=10, odds='1.50'):
    return [{'event': f'Match {i}', 'odds': D(odds)} for i in range(n)]


class _BonusBase(TestCase):
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


class BonusRuleTests(_BonusBase):
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
        self.assertEqual((b['bonus'], b['winnings']), ('0.00', '50.00'))    # 5× the $10 bonus
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



class ConversionCapTests(_BonusBase):
    """The unlock limit: the lower of the fixed cap and N× the bonus given."""

    def set_rules(self, **kw):
        WalletRules.objects.filter(pk=WalletRules.load().pk).update(**kw)

    def unlock(self):
        self.win(self.place())
        self.win(self.place())
        return self.bal()['winnings']

    def test_progress_shows_the_players_own_limit(self):
        self.assertEqual(bonus.progress(self.player.id)['max_conversion'], '50.00')
        self.set_rules(bonus_conversion_multiple=D('100'))
        self.assertEqual(bonus.progress(self.player.id)['max_conversion'], '500.00')   # fixed cap is lower

    def test_multiple_off_uses_the_fixed_cap(self):
        self.set_rules(bonus_conversion_multiple=D('0'))
        self.assertEqual(self.unlock(), '500.00')

    def test_multiple_one_unlocks_only_the_bonus_amount(self):
        self.set_rules(bonus_conversion_multiple=D('1'))
        self.assertEqual(self.unlock(), '10.00')

    def test_a_fixed_ten_dollar_cap(self):
        self.set_rules(bonus_conversion_multiple=D('0'), bonus_max_conversion=D('10'))
        self.assertEqual(self.unlock(), '10.00')

    def test_bonus_given_adds_up_and_a_loss_keeps_only_credits_after_the_bet(self):
        services.credit(player_id=self.player.id, amount=D('5'), kind='bonus', idempotency_key='b2')
        self.assertEqual(BonusRollover.objects.get(player_id=self.player.id).credited, D('15.00'))
        slip = self.place()                                       # stakes all $15
        services.credit(player_id=self.player.id, amount=D('4'), kind='bonus', idempotency_key='b3')
        self.lose(slip)
        self.assertEqual(BonusRollover.objects.get(player_id=self.player.id).credited, D('4.00'))
        self.assertEqual(bonus.progress(self.player.id)['max_conversion'], '20.00')

    def test_conversion_and_expiry_clear_the_bonus_given(self):
        self.unlock()
        self.assertEqual(BonusRollover.objects.get(player_id=self.player.id).credited, D('0.00'))
        services.credit(player_id=self.player.id, amount=D('8'), kind='bonus', idempotency_key='b4')
        bonus.reset(self.player.id, cleared=True)
        self.assertEqual(BonusRollover.objects.get(player_id=self.player.id).credited, D('0.00'))
