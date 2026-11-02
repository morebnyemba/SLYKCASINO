"""The Bonus wallet's rules, enforced here for every bet and settlement.

- Sportsbook only: never Aviator or casino games.
- A bonus ticket stakes the whole Bonus wallet (100% of it) on one multiple of
  at least `bonus_min_legs` selections (10), each priced at least
  `bonus_min_leg_odds` (1.50). No singles, no cash-out.
- A winning bonus ticket pays back into the Bonus wallet, not Winnings.
- After `bonus_wins_to_convert` (2) full-stake bonus tickets win in a row, the
  Bonus wallet moves to Winnings — up to `bonus_max_conversion` ($500); the
  rest is forfeited. A losing bonus ticket, or a new bonus credit, starts the
  count again.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Iterable

from django.db import transaction

from . import services, utils
from .models import BonusRollover, Bucket, WalletRules


def check_ticket(player_id: int, *, stake, leg_odds: Iterable, is_multiple: bool) -> None:
    """Refuse a bonus ticket that breaks the rules (WalletRuleError, shown to the player)."""
    rules = WalletRules.load()
    odds = [Decimal(str(o)) for o in leg_odds]
    if not is_multiple or len(odds) < rules.bonus_min_legs:
        raise services.WalletRuleError(
            f'Bonus bets must be one multiple of at least {rules.bonus_min_legs} selections.')
    low = [o for o in odds if o < rules.bonus_min_leg_odds]
    if low:
        raise services.WalletRuleError(
            f'Every selection on a bonus bet needs odds of at least {rules.bonus_min_leg_odds:.2f} '
            f'({len(low)} on this ticket don’t).')
    balance = services.get_balances(player_id)[Bucket.BONUS]
    if balance <= 0:
        raise services.WalletRuleError('Your Bonus wallet is empty.')
    if utils.quantize(stake) != balance:
        raise services.WalletRuleError(
            f'A bonus bet stakes your whole Bonus wallet: ${balance:.2f}.')


def not_for_games(wallet) -> None:
    """Aviator and casino games can't be played with bonus money."""
    if wallet == Bucket.BONUS:
        raise services.WalletRuleError('Bonus money can only be used on sports bets.')


def progress(player_id: int) -> dict:
    rules = WalletRules.load()
    wins = BonusRollover.objects.filter(player_id=player_id).values_list('wins', flat=True).first() or 0
    return {'wins': wins, 'wins_needed': rules.bonus_wins_to_convert,
            'max_conversion': str(rules.bonus_max_conversion),
            'min_legs': rules.bonus_min_legs, 'min_leg_odds': str(rules.bonus_min_leg_odds)}


def reset(player_id: int) -> None:
    BonusRollover.objects.filter(player_id=player_id).update(wins=0)


@transaction.atomic
def ticket_settled(player_id: int, *, won: bool, ticket: str) -> None:
    """Count a settled bonus ticket. A win towards the rollover; a loss starts
    it again. Enough wins in a row convert the Bonus wallet to Winnings."""
    row, _ = BonusRollover.objects.select_for_update().get_or_create(player_id=player_id)
    if not won:
        row.wins = 0
        row.save(update_fields=['wins', 'updated_at'])
        return
    row.wins += 1
    rules = WalletRules.load()
    if row.wins < rules.bonus_wins_to_convert:
        row.save(update_fields=['wins', 'updated_at'])
        return
    row.wins = 0
    row.save(update_fields=['wins', 'updated_at'])
    _convert(player_id, rules, ticket=ticket)


def _convert(player_id: int, rules: WalletRules, *, ticket: str) -> None:
    balance = services.get_balances(player_id)[Bucket.BONUS]
    if balance <= 0:
        return
    converted = min(balance, rules.bonus_max_conversion)
    forfeited = balance - converted
    key = f'bonus-conversion:{ticket}'
    services.post_entry(player_id=player_id, amount=-converted, kind='bonus_conversion', bucket=Bucket.BONUS,
                        idempotency_key=f'{key}:out', reference=ticket, require_non_negative=True)
    services.post_entry(player_id=player_id, amount=converted, kind='bonus_conversion', bucket=Bucket.WINNINGS,
                        idempotency_key=f'{key}:in', reference=ticket)
    if forfeited > 0:
        services.post_entry(player_id=player_id, amount=-forfeited, kind='bonus_forfeit', bucket=Bucket.BONUS,
                            idempotency_key=f'{key}:forfeit', reference=ticket, require_non_negative=True)
    from apps.notifications import services as notif_services
    notif_services.notify(
        player_id=player_id, kind='bonus_credited', title='Bonus unlocked',
        body=(f'${converted:.2f} of bonus winnings moved to your Winnings wallet — it’s yours to withdraw.'
              + (f' ${forfeited:.2f} above the ${rules.bonus_max_conversion:.2f} limit was forfeited.' if forfeited else '')),
    )
