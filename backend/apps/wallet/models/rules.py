from decimal import Decimal

from django.db import models


class WalletRules(models.Model):
    """Operator rules for betting from each wallet (one row): the lowest
    combined odds a ticket may have to be paid for from that balance."""
    deposit_min_odds = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('5.00'))
    bonus_min_odds = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('10.00'))
    winnings_min_odds = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('1.00'))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'wallet_rules'

    @classmethod
    def load(cls) -> 'WalletRules':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def min_odds(self, bucket: str) -> Decimal:
        return getattr(self, f'{bucket}_min_odds')
