from django.db import models


class Wallet(models.Model):
    """A player's wallet. `player_id` is an integer reference to accounts.Player
    (no cross-app FK — bounded contexts integrate by ID). `balance` is a cached
    aggregate of the ledger, kept correct by services and audited by recovery."""

    player_id = models.BigIntegerField(unique=True, db_index=True)
    currency = models.CharField(max_length=8, default='USD')
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'wallet_wallet'

    def __str__(self) -> str:
        return f'wallet(player={self.player_id}, {self.balance} {self.currency})'
