from django.db import models


class Event(models.Model):
    """A betting market/event."""

    name = models.CharField(max_length=200)
    odds = models.DecimalField(max_digits=6, decimal_places=2, default=1.95)
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
