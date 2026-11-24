from decimal import Decimal

from django.db import models


class LossRefundSettings(models.Model):
    """A multiple lost by exactly one match gets part of it back (promotions.refunds):
    stake × ticket odds ÷ `divisor` ÷ the lost match's odds, when the ticket's odds
    are above `min_odds`. Paid to Winnings."""
    enabled = models.BooleanField(default=True)
    min_odds = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('25.00'))
    divisor = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('25.00'))
    # The most one refund can be (blank = no limit).
    max_refund = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def load(cls) -> 'LossRefundSettings':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class CashbackSettings(models.Model):
    """Cashback on losses (promotions.cashback): every `period_days` days from
    `starts_on`, each player whose real-money losses, tickets and playing days in
    that period meet a tier gets that tier's % of the loss back, to Winnings."""
    enabled = models.BooleanField(default=False)
    period_days = models.PositiveSmallIntegerField(default=7)
    starts_on = models.DateField(null=True, blank=True)
    # The last period paid (its first day), so each period is paid once.
    last_period_start = models.DateField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def load(cls) -> 'CashbackSettings':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class CashbackTier(models.Model):
    """One rule: lose at least `min_loss` over the period, with `min_tickets`
    tickets on at least `min_active_days` days, and get `percent` back (up to
    `max_amount`). A player gets the best tier they meet."""
    name = models.CharField(max_length=60, blank=True, default='')
    min_loss = models.DecimalField(max_digits=12, decimal_places=2)
    percent = models.DecimalField(max_digits=5, decimal_places=2)
    max_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    min_tickets = models.PositiveIntegerField(default=0)
    min_active_days = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)

    class Meta:
        ordering = ['min_loss', 'id']


class CashbackPayout(models.Model):
    player_id = models.BigIntegerField(db_index=True)
    period_start = models.DateField()
    period_end = models.DateField()
    loss = models.DecimalField(max_digits=14, decimal_places=2)
    tickets = models.PositiveIntegerField(default=0)
    active_days = models.PositiveSmallIntegerField(default=0)
    tier = models.ForeignKey(CashbackTier, null=True, on_delete=models.SET_NULL)
    percent = models.DecimalField(max_digits=5, decimal_places=2)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['player_id', 'period_start'], name='one_cashback_per_player_period')]
