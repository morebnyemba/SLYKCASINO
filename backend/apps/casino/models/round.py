from django.db import models

from apps.wallet.models.wallet import Bucket


class GameRound(models.Model):
    """A single play. `player_id` references accounts.Player by ID.

    Lifecycle: PENDING (stake debit not confirmed) -> SETTLED (win applied) /
    VOID. `debit_confirmed` records whether the wallet debit landed — the hook
    recovery uses to retry a stuck debit sequence idempotently."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending (debit unconfirmed)'
        SETTLED = 'settled', 'Settled'
        VOID = 'void', 'Void'

    player_id = models.BigIntegerField(db_index=True)
    game = models.ForeignKey('casino.Game', on_delete=models.PROTECT, related_name='rounds')
    stake = models.DecimalField(max_digits=12, decimal_places=2)
    # The wallet (deposit / bonus / winnings) the stake was paid from: refunds
    # and the stake part of a win go back there, only profit goes to winnings.
    wallet = models.CharField(max_length=10, choices=Bucket.choices)
    win = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    debit_confirmed = models.BooleanField(default=False)
    provider_round_ref = models.CharField(max_length=200, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'casino_round'
        constraints = [
            models.CheckConstraint(check=models.Q(wallet__in=Bucket.values), name='casino_round_wallet_valid'),
        ]
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', 'debit_confirmed', 'created_at'])]

    def __str__(self) -> str:
        return f'round({self.game_id}, player={self.player_id}, {self.status})'
