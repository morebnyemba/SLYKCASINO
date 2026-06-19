from django.db import models


class Game(models.Model):
    """A casino game in the catalog (provider-backed)."""

    class Category(models.TextChoices):
        SLOTS = 'slots', 'Slots'
        CRASH = 'crash', 'Crash'
        LIVE = 'live', 'Live Casino'
        TABLE = 'table', 'Table Games'
        VIRTUAL = 'virtual', 'Virtual Sports'
        INSTANT = 'instant', 'Instant Win'

    slug = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=200)
    provider = models.CharField(max_length=80, default='stub')
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.SLOTS, db_index=True)
    rtp = models.DecimalField(max_digits=5, decimal_places=2, default=96.0)  # %
    is_active = models.BooleanField(default=True)
    image_url = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = 'casino_game'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name
