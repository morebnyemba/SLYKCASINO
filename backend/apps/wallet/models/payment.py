from django.db import models


class PaymentTransaction(models.Model):
    """A deposit taken through an external payment gateway (Paynow). Created
    pending when the player starts paying; the wallet is credited once, when
    the gateway reports it paid (result callback or a status poll)."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending'
        PAID = 'paid', 'Paid (credited)'
        FAILED = 'failed', 'Failed'
        CANCELLED = 'cancelled', 'Cancelled'

    reference = models.CharField(max_length=40, unique=True)
    player_id = models.BigIntegerField(db_index=True)
    provider = models.CharField(max_length=20, default='paynow')
    method = models.CharField(max_length=20)
    phone = models.CharField(max_length=20, blank=True)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    currency = models.CharField(max_length=8, default='USD')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True)
    provider_ref = models.CharField(max_length=64, blank=True)
    provider_status = models.CharField(max_length=40, blank=True)
    poll_url = models.URLField(max_length=500, blank=True)
    redirect_url = models.URLField(max_length=500, blank=True)
    instructions = models.TextField(blank=True)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'wallet_paymenttransaction'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.reference} {self.method} {self.amount} ({self.status})'
