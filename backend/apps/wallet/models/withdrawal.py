from decimal import Decimal

from django.db import models


class WithdrawalSettings(models.Model):
    """Operator limits for player withdrawals (one row)."""
    min_amount = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1.00'))
    max_amount = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('1000.00'))
    # Most one player may request in a day (0 = no daily cap).
    daily_max = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('2000.00'))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'wallet_withdrawal_settings'

    @classmethod
    def load(cls) -> 'WithdrawalSettings':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class WithdrawalRequest(models.Model):
    """A player's request to be paid out. The money is held off their balance
    as soon as they ask (ledger kind `withdrawal_hold`); staff send it by hand
    and mark it paid (it then posts as a `withdrawal`), or reject it and the
    hold is returned. So `withdrawal` entries — what reports count — are only
    money that actually went out."""

    class Method(models.TextChoices):
        ECOCASH = 'ecocash', 'EcoCash'
        ONEMONEY = 'onemoney', 'OneMoney'
        INNBUCKS = 'innbucks', 'InnBucks'
        BANK = 'bank', 'Bank transfer'

    class Status(models.TextChoices):
        REQUESTED = 'requested', 'Waiting to be paid'
        PAID = 'paid', 'Paid'
        REJECTED = 'rejected', 'Rejected'
        CANCELLED = 'cancelled', 'Cancelled'

    player_id = models.BigIntegerField(db_index=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    method = models.CharField(max_length=10, choices=Method.choices)
    account_name = models.CharField(max_length=120, blank=True)
    account_number = models.CharField(max_length=60)
    bank_name = models.CharField(max_length=80, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.REQUESTED, db_index=True)
    # The EcoCash/bank transaction reference staff entered when paying.
    reference = models.CharField(max_length=120, blank=True)
    # Why it was rejected (shown to the player) or a staff note.
    note = models.CharField(max_length=300, blank=True)
    decided_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    decided_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'wallet_withdrawal_request'
        ordering = ['-id']

    def __str__(self) -> str:
        return f'Withdrawal {self.id}: {self.amount} to {self.method} ({self.status})'
