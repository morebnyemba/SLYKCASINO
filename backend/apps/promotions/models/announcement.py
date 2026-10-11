from django.db import models


class SiteAnnouncement(models.Model):
    """A notice bar across the top of every page (one row), e.g. service updates.
    Staff edit it under Admin → Banners."""

    class Tone(models.TextChoices):
        INFO = 'info', 'Information'
        WARNING = 'warning', 'Important'

    enabled = models.BooleanField(default=False)
    title = models.CharField(max_length=80, blank=True)
    message = models.TextField(max_length=600, blank=True)
    tone = models.CharField(max_length=10, choices=Tone.choices, default=Tone.WARNING)
    # Buttons on the bar.
    show_withdraw_button = models.BooleanField(default=False)
    show_support_button = models.BooleanField(default=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = 'promotions_site_announcement'

    @classmethod
    def load(cls) -> 'SiteAnnouncement':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
