from django.db import models
from django.db.models import F, Q


class Bucket(models.TextChoices):
    """The three independent balances every player has.

    DEPOSIT — money the player paid in. Can be bet, never withdrawn by the player.
    BONUS — promotional money. Can be bet, never withdrawn.
    WINNINGS — profit from bets (and affiliate commission). The only
    withdrawable balance."""
    DEPOSIT = 'deposit', 'Deposit'
    BONUS = 'bonus', 'Bonus'
    WINNINGS = 'winnings', 'Winnings'


BALANCE_FIELD = {
    Bucket.DEPOSIT: 'deposit_balance',
    Bucket.BONUS: 'bonus_balance',
    Bucket.WINNINGS: 'winnings_balance',
}


class Wallet(models.Model):
    """A player's wallet. `player_id` is an integer reference to accounts.Player
    (no cross-app FK — bounded contexts integrate by ID). The three bucket
    balances are cached aggregates of the ledger (per bucket), kept correct by
    services and audited by recovery; `balance` is their total."""

    player_id = models.BigIntegerField(unique=True, db_index=True)
    currency = models.CharField(max_length=8, default='USD')
    deposit_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    bonus_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    winnings_balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    balance = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'wallet_wallet'
        constraints = [
            # Last line of defense against overdraft: application-level locking
            # (wallet.services.post_entry) is the primary guard; these make a
            # balance-corrupting bug fail loudly instead of persisting.
            models.CheckConstraint(check=Q(balance__gte=0), name='wallet_balance_non_negative'),
            models.CheckConstraint(check=Q(deposit_balance__gte=0), name='wallet_deposit_non_negative'),
            models.CheckConstraint(check=Q(bonus_balance__gte=0), name='wallet_bonus_non_negative'),
            models.CheckConstraint(check=Q(winnings_balance__gte=0), name='wallet_winnings_non_negative'),
            models.CheckConstraint(
                check=Q(balance=F('deposit_balance') + F('bonus_balance') + F('winnings_balance')),
                name='wallet_balance_is_sum_of_buckets',
            ),
        ]

    def __str__(self) -> str:
        return (f'wallet(player={self.player_id}, deposit {self.deposit_balance}, bonus {self.bonus_balance}, '
                f'winnings {self.winnings_balance} {self.currency})')

    def bucket_balance(self, bucket: str):
        return getattr(self, BALANCE_FIELD[bucket])
