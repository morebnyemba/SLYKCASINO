from django.db import models

from .bet import Selection


class BetSlip(models.Model):
    """A multi-leg accumulator: one stake across several selections, where the
    combined odds are the product of every leg and ALL legs must win to pay out.
    A single stake is debited at placement; settlement resolves once no leg is
    still pending."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending (stake not confirmed)'
        OPEN = 'open', 'Open'
        WON = 'won', 'Won'
        LOST = 'lost', 'Lost'
        VOID = 'void', 'Void'

    player_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    stake = models.DecimalField(max_digits=12, decimal_places=2)
    combined_odds = models.DecimalField(max_digits=12, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    payout = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    placed_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'sportsbook_betslip'
        ordering = ['-placed_at']
        indexes = [models.Index(fields=['status', 'placed_at'])]

    def __str__(self) -> str:
        return f'Acca #{self.pk} x{self.combined_odds} ({self.status})'


class BetLeg(models.Model):
    """One selection within an accumulator slip."""

    class Result(models.TextChoices):
        PENDING = 'pending', 'Pending'
        WON = 'won', 'Won'
        LOST = 'lost', 'Lost'
        VOID = 'void', 'Void'

    slip = models.ForeignKey(BetSlip, on_delete=models.CASCADE, related_name='legs')
    event = models.CharField(max_length=200)
    event_ref = models.ForeignKey(
        'Event', null=True, blank=True, on_delete=models.SET_NULL, related_name='legs',
    )
    selection = models.CharField(max_length=10, choices=Selection.choices, default=Selection.HOME)
    odds = models.DecimalField(max_digits=6, decimal_places=2)
    result = models.CharField(max_length=10, choices=Result.choices, default=Result.PENDING)

    class Meta:
        db_table = 'sportsbook_betleg'
        ordering = ['id']

    def __str__(self) -> str:
        return f'{self.event} @ {self.odds} ({self.result})'
