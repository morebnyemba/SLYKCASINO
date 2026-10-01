from django.db import models
from django.db.models import Q


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
        constraints = [
            # Last line of defense against overdraft: application-level locking
            # (wallet.services.post_entry) is the primary guard, this constraint
            # is what makes a balance-corrupting bug fail loudly instead of
            # silently persisting a negative balance.
            models.CheckConstraint(check=Q(balance__gte=0), name='wallet_balance_non_negative'),
        ]

    def __str__(self) -> str:
        return f'wallet(player={self.player_id}, {self.balance} {self.currency})'
