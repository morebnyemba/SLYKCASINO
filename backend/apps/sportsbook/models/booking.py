from django.db import models


class BookingCode(models.Model):
    """A shareable bet slip: the picks only (no stake, no prices), looked up by a
    short code so a slip can be passed around on WhatsApp and loaded by anyone.
    Prices are read fresh when the code is loaded.

    `selections` is a list of {"event_id", "selection"} for 1X2 picks or
    {"outcome_id"} for secondary-market picks."""

    code = models.CharField(max_length=12, unique=True)
    selections = models.JSONField(default=list)
    player_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    loads = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sportsbook_bookingcode'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return f'{self.code} ({len(self.selections)} picks)'


class MultiBetBonusTier(models.Model):
    """Accumulator bonus ladder: a winning multiple with at least `min_legs`
    qualifying legs (each priced at or above SPORTSBOOK_ACCA_BONUS_MIN_ODDS) gets
    `percent` added to its winnings. The highest tier reached applies."""

    min_legs = models.PositiveSmallIntegerField(unique=True)
    percent = models.DecimalField(max_digits=5, decimal_places=2)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'sportsbook_multibetbonustier'
        ordering = ['min_legs']

    def __str__(self) -> str:
        return f'{self.min_legs}+ legs: {self.percent}%'
