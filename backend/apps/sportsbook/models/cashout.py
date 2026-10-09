from django.db import models


class CashoutSettings(models.Model):
    """Operator controls for cash-out (one row, edited in the admin console)."""
    enabled = models.BooleanField(default=True)
    allow_partial = models.BooleanField(default=True)
    in_play = models.BooleanField(default=True, help_text='Offer cash-out while matches are being played.')
    # Taken off the fair value of the ticket at current prices.
    margin_percent = models.DecimalField(max_digits=5, decimal_places=2, default=5)
    # Offers below this are not shown, and partial cash-outs can't go below it.
    min_amount = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sportsbook_cashout_settings'

    @classmethod
    def load(cls) -> 'CashoutSettings':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class Cashout(models.Model):
    """One cash-out taken on a single bet or an accumulator slip. Its id keys
    the wallet credit, so a retried request can never pay twice."""
    bet = models.ForeignKey('Bet', null=True, blank=True, on_delete=models.CASCADE, related_name='cashouts')
    slip = models.ForeignKey('BetSlip', null=True, blank=True, on_delete=models.CASCADE, related_name='cashouts')
    player_id = models.BigIntegerField(db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    stake_portion = models.DecimalField(max_digits=12, decimal_places=2)
    full = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sportsbook_cashout'
        ordering = ['-created_at']

    def __str__(self) -> str:
        target = f'bet {self.bet_id}' if self.bet_id else f'slip {self.slip_id}'
        return f'Cash-out {self.amount} on {target}'
