from django.db import models


class TicketReversal(models.Model):
    """Staff took back a ticket's winnings because it was settled as won by
    mistake. One per ticket. `owed` is what was paid out and should come back;
    `recovered` is what the player's wallets still held; `shortfall` is the rest
    (already withdrawn or bet), which stays on record against the player."""

    class Kind(models.TextChoices):
        SINGLE = 'single', 'Single'
        MULTIPLE = 'multiple', 'Multiple'

    class Outcome(models.TextChoices):
        LOST = 'lost', 'Lost (payout and stake taken back)'
        VOID = 'void', 'Void (winnings taken back, stake stays returned)'

    kind = models.CharField(max_length=10, choices=Kind.choices)
    ticket_id = models.BigIntegerField()
    player_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    outcome = models.CharField(max_length=6, choices=Outcome.choices)
    paid = models.DecimalField(max_digits=14, decimal_places=2)
    owed = models.DecimalField(max_digits=14, decimal_places=2)
    recovered = models.DecimalField(max_digits=14, decimal_places=2)
    shortfall = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    # What came out of each wallet: {"winnings": "40.00", "deposit": "10.00"}.
    taken = models.JSONField(default=dict)
    reason = models.CharField(max_length=300)
    reversed_by = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sportsbook_ticket_reversal'
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['kind', 'ticket_id'], name='one_reversal_per_ticket')]
