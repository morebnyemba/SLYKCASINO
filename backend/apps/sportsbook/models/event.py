from django.db import models


class Event(models.Model):
    """A betting market/event."""

    class Sport(models.TextChoices):
        FOOTBALL = 'football', 'Football'
        BASKETBALL = 'basketball', 'Basketball'
        TENNIS = 'tennis', 'Tennis'
        MMA = 'mma', 'MMA'
        BOXING = 'boxing', 'Boxing'
        BASEBALL = 'baseball', 'Baseball'
        ATHLETICS = 'athletics', 'Athletics'
        ESPORTS = 'esports', 'Esports'

    name = models.CharField(max_length=200)
    sport = models.CharField(max_length=20, choices=Sport.choices, default=Sport.FOOTBALL, db_index=True)
    # Maps this event to a fixture in an external provider (e.g. api-football's
    # fixture id) so scheduled syncs can find and update it. Null for events
    # created without a provider feed (e.g. seeded/manual markets).
    external_id = models.CharField(max_length=32, null=True, blank=True, db_index=True)
    provider = models.CharField(max_length=20, default='', blank=True)
    # `odds` is the "1" (home/outcome-A) price. `odds_draw`/`odds_away` are
    # optional — set for true 1/X/2 markets (e.g. football); left null for
    # two-outcome sports (e.g. tennis, basketball) which only use `odds`
    # as the "favourite" price shown in single-odds listings.
    odds = models.DecimalField(max_digits=6, decimal_places=2, default=1.95)
    odds_draw = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    odds_away = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    previous_odds = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    featured = models.BooleanField(default=False)
    is_open = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'sportsbook_event'
        ordering = ['-featured', 'name']

    def __str__(self) -> str:
        return self.name

    def save(self, *args, **kwargs):
        if self.pk:
            prior = Event.objects.filter(pk=self.pk).values_list('odds', flat=True).first()
            if prior is not None and prior != self.odds:
                self.previous_odds = prior
        super().save(*args, **kwargs)
