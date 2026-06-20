from django.db import models
from django.utils import timezone


class Banner(models.Model):
    """A wide promotional / site banner rendered on player-facing surfaces.

    Operators manage these from the admin app (or Django admin). `placement`
    selects where the banner appears; `sort_order` controls ordering within a
    placement; `starts_at`/`ends_at` optionally schedule it."""

    class Placement(models.TextChoices):
        HOME_HERO = 'home_hero', 'Homepage hero'

    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=300, blank=True)
    image_url = models.CharField(max_length=500)
    link_url = models.CharField(max_length=500, blank=True)
    cta_label = models.CharField(max_length=60, blank=True)
    placement = models.CharField(max_length=20, choices=Placement.choices, default=Placement.HOME_HERO)
    sort_order = models.IntegerField(default=0)
    active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'promotions_banner'
        ordering = ['sort_order', '-created_at']

    def __str__(self) -> str:
        return self.title

    @property
    def is_live(self) -> bool:
        now = timezone.now()
        if not self.active:
            return False
        if self.starts_at and now < self.starts_at:
            return False
        if self.ends_at and now > self.ends_at:
            return False
        return True
