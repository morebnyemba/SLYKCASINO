from django.db import models


class Selection(models.TextChoices):
    """Which outcome a wager backs. For two-outcome markets (e.g. tennis) only
    HOME is used; 1/X/2 markets use all three."""
    HOME = 'home', 'Home / 1'
    DRAW = 'draw', 'Draw / X'
    AWAY = 'away', 'Away / 2'


class Bet(models.Model):
    """A wager. `player_id` is an integer reference to accounts.Player (no
    cross-app FK). Lifecycle: PENDING (created, stake not yet debited) ->
    OPEN (stake debited, awaiting result) -> WON/LOST/VOID."""

    class Status(models.TextChoices):
        PENDING = 'pending', 'Pending (stake not confirmed)'
        OPEN = 'open', 'Open'
        WON = 'won', 'Won'
        LOST = 'lost', 'Lost'
        VOID = 'void', 'Void'

    player_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    event = models.CharField(max_length=200)            # market identifier/label
    # Soft link back to the market so a result can settle every bet on it at once.
    # Nullable: legacy/anonymous free-text bets keep working without a link.
    event_ref = models.ForeignKey(
        'Event', null=True, blank=True, on_delete=models.SET_NULL, related_name='bets',
    )
    selection = models.CharField(max_length=10, choices=Selection.choices, default=Selection.HOME)
    stake = models.DecimalField(max_digits=12, decimal_places=2)
    odds = models.DecimalField(max_digits=6, decimal_places=2)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    payout = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    placed_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'sportsbook_bet'
        ordering = ['-placed_at']
        indexes = [models.Index(fields=['status', 'placed_at'])]

    def __str__(self) -> str:
        return f'{self.event} @ {self.odds} ({self.status})'
