from django.db import models


class Event(models.Model):
    """A betting market/event."""

    name = models.CharField(max_length=200)
    odds = models.DecimalField(max_digits=6, decimal_places=2, default=1.95)
    featured = models.BooleanField(default=False)
    is_open = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'sportsbook_event'
        ordering = ['-featured', 'name']

    def __str__(self) -> str:
        return self.name
