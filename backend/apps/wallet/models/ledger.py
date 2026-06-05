from django.db import models


class LedgerEntry(models.Model):
    """Append-only, signed money movement.

    `idempotency_key` is UNIQUE — this is the linchpin of safe retries and
    idempotent recovery: re-posting the same logical operation collides here and
    is a no-op. `amount` is signed (negative = debit). Entries are never updated
    or deleted; corrections are new compensating entries.
    """

    class Kind(models.TextChoices):
        DEPOSIT = 'deposit', 'Deposit'
        WITHDRAWAL = 'withdrawal', 'Withdrawal'
        BET_STAKE = 'bet_stake', 'Bet stake (debit)'
        BET_PAYOUT = 'bet_payout', 'Bet payout (credit)'
        CASINO_DEBIT = 'casino_debit', 'Casino debit'
        CASINO_CREDIT = 'casino_credit', 'Casino credit'
        BONUS = 'bonus', 'Bonus credit'
        ADJUSTMENT = 'adjustment', 'Manual adjustment'

    wallet = models.ForeignKey(
        'wallet.Wallet', on_delete=models.CASCADE, related_name='entries',
    )
    idempotency_key = models.CharField(max_length=200, unique=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)  # signed
    kind = models.CharField(max_length=20, choices=Kind.choices)
    reference = models.CharField(max_length=200, blank=True)  # e.g. "bet:42"
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'wallet_ledger_entry'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['wallet', 'created_at']),
            models.Index(fields=['reference']),
        ]

    def __str__(self) -> str:
        return f'{self.kind} {self.amount} [{self.idempotency_key}]'
