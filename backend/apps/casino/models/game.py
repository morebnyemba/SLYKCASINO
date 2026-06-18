from django.db import models


class Game(models.Model):
    """A casino game in the catalog (provider-backed)."""

    slug = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=200)
    provider = models.CharField(max_length=80, default='stub')
    rtp = models.DecimalField(max_digits=5, decimal_places=2, default=96.0)  # %
    is_active = models.BooleanField(default=True)
    image_url = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = 'casino_game'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name
