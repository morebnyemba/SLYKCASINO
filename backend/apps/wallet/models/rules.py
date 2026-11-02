from decimal import Decimal

from django.db import models


class WalletRules(models.Model):
    """Operator rules for betting from each wallet (one row): the lowest
    combined odds a ticket may have to be paid for from that balance, and the
    Bonus wallet's rules (wallet.bonus)."""
    deposit_min_odds = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('5.00'))
    bonus_min_odds = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('10.00'))
    winnings_min_odds = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('1.00'))
    # Bonus tickets: sportsbook multiples only, the whole Bonus wallet staked,
    # at least this many selections, each at least these odds.
    bonus_min_legs = models.PositiveSmallIntegerField(default=10)
    bonus_min_leg_odds = models.DecimalField(max_digits=6, decimal_places=2, default=Decimal('1.50'))
    # Bonus winnings stay in the Bonus wallet until this many full-stake bonus
    # tickets win in a row; then the wallet moves to Winnings, up to the cap
    # (the rest is forfeited).
    bonus_wins_to_convert = models.PositiveSmallIntegerField(default=2)
    bonus_max_conversion = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('500.00'))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'wallet_rules'

    @classmethod
    def load(cls) -> 'WalletRules':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def min_odds(self, bucket: str) -> Decimal:
        return getattr(self, f'{bucket}_min_odds')


class BonusRollover(models.Model):
    """How many full-stake bonus tickets a player has won in a row. Reset by a
    losing bonus ticket, a new bonus credit, or a conversion."""
    player_id = models.BigIntegerField(unique=True)
    wins = models.PositiveSmallIntegerField(default=0)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'wallet_bonus_rollover'
