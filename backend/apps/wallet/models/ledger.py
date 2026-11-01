from django.db import models
from django.db.models import Q

from .wallet import Bucket

# Which balance each kind of movement may touch. Enforced by a database
# constraint (below) as well as by services, so no code path — or hand-written
# SQL — can e.g. pay a withdrawal out of the deposit balance or move deposit
# money into the bonus balance. Kinds not listed (stakes, payouts,
# adjustments) may touch any bucket; services route them.
FIXED_BUCKET = {
    'deposit': Bucket.DEPOSIT,
    'deposit_refund': Bucket.DEPOSIT,
    'bonus': Bucket.BONUS,
    'withdrawal': Bucket.WINNINGS,
    'withdrawal_hold': Bucket.WINNINGS,
    'withdrawal_fee': Bucket.WINNINGS,
    'affiliate': Bucket.WINNINGS,
}


def _bucket_rule() -> Q:
    rule = Q(legacy=True)
    for kind, bucket in FIXED_BUCKET.items():
        rule |= Q(kind=kind, bucket=bucket)
    return rule | ~Q(kind__in=list(FIXED_BUCKET))


class LedgerEntry(models.Model):
    """Append-only, signed money movement on one of the wallet's three buckets.

    `idempotency_key` is UNIQUE — this is the linchpin of safe retries and
    idempotent recovery: re-posting the same logical operation collides here and
    is a no-op. `amount` is signed (negative = debit). Entries are never updated
    or deleted (on Postgres a trigger refuses it); corrections are new
    compensating entries. `legacy` marks rows from before the three-wallet
    split, which the bucket rules don't apply to.
    """

    class Kind(models.TextChoices):
        DEPOSIT = 'deposit', 'Deposit'
        # Unplayed deposit money returned by staff (account closure /
        # self-exclusion) to the number it came from — never player-initiated.
        DEPOSIT_REFUND = 'deposit_refund', 'Deposit refund'
        WITHDRAWAL = 'withdrawal', 'Withdrawal'
        # Held for a pending withdrawal request; returned if it's rejected or
        # cancelled, released into a `withdrawal` when staff pay it.
        WITHDRAWAL_HOLD = 'withdrawal_hold', 'Withdrawal held'
        WITHDRAWAL_FEE = 'withdrawal_fee', 'Withdrawal fee'
        BET_STAKE = 'bet_stake', 'Bet stake (debit)'
        BET_PAYOUT = 'bet_payout', 'Bet payout (credit)'
        CASINO_DEBIT = 'casino_debit', 'Casino debit'
        CASINO_CREDIT = 'casino_credit', 'Casino credit'
        BONUS = 'bonus', 'Bonus credit'
        ADJUSTMENT = 'adjustment', 'Manual adjustment'
        AFFILIATE = 'affiliate', 'Affiliate commission'
        # Only the one-off move of pre-split balances into the buckets.
        MIGRATION = 'migration', 'Wallet split'

    wallet = models.ForeignKey(
        'wallet.Wallet', on_delete=models.CASCADE, related_name='entries',
    )
    idempotency_key = models.CharField(max_length=200, unique=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)  # signed
    kind = models.CharField(max_length=20, choices=Kind.choices)
    bucket = models.CharField(max_length=10, choices=Bucket.choices)
    legacy = models.BooleanField(default=False)
    reference = models.CharField(max_length=200, blank=True)  # e.g. "bet:42"
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'wallet_ledger_entry'
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['wallet', 'created_at']),
            models.Index(fields=['reference']),
            models.Index(fields=['wallet', 'bucket'], name='wallet_ledg_wallet__bucket_idx'),
        ]
        constraints = [
            models.CheckConstraint(check=_bucket_rule(), name='ledger_kind_bucket_allowed'),
            models.CheckConstraint(
                check=Q(legacy=True) | ~Q(kind='deposit') | Q(amount__gt=0), name='ledger_deposit_is_credit'),
            models.CheckConstraint(
                check=Q(legacy=True) | ~Q(kind__in=['bet_stake', 'casino_debit', 'deposit_refund', 'withdrawal_fee'])
                | Q(amount__lte=0), name='ledger_stake_is_debit'),
            models.CheckConstraint(
                check=Q(legacy=True) | ~Q(kind__in=['bet_payout', 'casino_credit', 'bonus', 'affiliate'])
                | Q(amount__gte=0), name='ledger_payout_is_credit'),
            models.CheckConstraint(check=Q(legacy=True) | ~Q(kind='migration'), name='ledger_migration_only_legacy'),
        ]

    def __str__(self) -> str:
        return f'{self.kind} {self.amount} {self.bucket} [{self.idempotency_key}]'

    @property
    def transaction_ref(self) -> str:
        """The unique reference shown to players and staff, e.g. BB-0000042."""
        return f'BB-{self.pk:07d}'
