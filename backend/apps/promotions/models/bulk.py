from decimal import Decimal

from django.db import models


class BulkGrant(models.Model):
    """One promotion applied to many players at once by staff: a bonus credited
    to (or bonus taken back from) every player in an audience. Runs in the
    background and can be re-run safely: each player is paid at most once per
    grant (promotions.bulk)."""

    class Kind(models.TextChoices):
        CREDIT = 'credit', 'Give a bonus'
        DEBIT = 'debit', 'Take back bonus'

    class Audience(models.TextChoices):
        ALL = 'all', 'All players'
        DEPOSITORS = 'depositors', 'Players who have deposited'
        ACTIVE = 'active', 'Players who bet in the last 30 days'
        VERIFIED = 'verified', 'Verified players'

    class Status(models.TextChoices):
        RUNNING = 'running', 'Running'
        DONE = 'done', 'Done'
        FAILED = 'failed', 'Failed'

    kind = models.CharField(max_length=8, choices=Kind.choices)
    audience = models.CharField(max_length=12, choices=Audience.choices, default=Audience.ALL)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    wagering_multiplier = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('1.00'))
    name = models.CharField(max_length=80)                  # shown to players ("Weekend boost")
    message = models.CharField(max_length=300, blank=True, default='')
    # Set on the batch that takes back what another one gave (Undo).
    undo_of = models.OneToOneField('self', null=True, blank=True, on_delete=models.PROTECT, related_name='undone_by')
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.RUNNING, db_index=True)
    players = models.PositiveIntegerField(default=0)        # in the audience when it started
    processed = models.PositiveIntegerField(default=0)
    affected = models.PositiveIntegerField(default=0)       # actually credited / debited
    skipped = models.PositiveIntegerField(default=0)        # refused by fraud checks, or no bonus to take
    total = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal('0.00'))
    error = models.CharField(max_length=300, blank=True, default='')
    created_by = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)
    heartbeat_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-id']

    def __str__(self) -> str:
        return f'{self.get_kind_display()} ${self.amount} · {self.name}'
