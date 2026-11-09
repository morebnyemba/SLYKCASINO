from django.db import models
from django.utils import timezone


class Banner(models.Model):
    """A wide promotional / site banner rendered on player-facing surfaces.

    Operators manage these from the admin app (or Django admin). `placement`
    selects where the banner appears; `sort_order` controls ordering within a
    placement; `starts_at`/`ends_at` optionally schedule it."""

    class Placement(models.TextChoices):
        HOME_HERO = 'home_hero', 'Homepage hero'
        SPORTSBOOK = 'sportsbook', 'Sportsbook'

    class Focus(models.TextChoices):
        LEFT = 'left', 'Left'
        CENTER = 'center', 'Centre'
        RIGHT = 'right', 'Right'

    class Motion(models.TextChoices):
        NONE = 'none', 'None'
        ZOOM = 'zoom', 'Slow zoom'
        SHINE = 'shine', 'Sweeping shine'

    title = models.CharField(max_length=200)
    subtitle = models.CharField(max_length=300, blank=True)
    image_url = models.CharField(max_length=500)
    # A design made for phones (about 16:10). Shown instead of `image_url` on
    # small screens; without one the wide design is cropped to fit.
    mobile_image_url = models.CharField(max_length=500, blank=True)
    # Which part of the wide design stays in view when it is cropped for a phone.
    focus = models.CharField(max_length=6, choices=Focus.choices, default=Focus.CENTER)
    # A short silent loop (MP4 or WebM) played over the image, which stays as
    # its poster and as the fallback where video is off (reduced motion, data
    # saver, an error). Animated GIF/WebP images need no video.
    video_url = models.CharField(max_length=500, blank=True)
    # Movement for a still banner: a slow zoom on the image, or a sheen sweeping across.
    motion = models.CharField(max_length=6, choices=Motion.choices, default=Motion.NONE)
    # Print the title, subtitle and a dark fade over the image. Turn off when the
    # design already carries its own words (only the button is added on top).
    overlay_text = models.BooleanField(default=True)
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


class BannerImage(models.Model):
    """A banner design uploaded from the operator console. Stored in the
    database (not on the container's disk) so it survives redeploys, and
    served publicly at /api/promotions/banner-images/<id>/."""

    content = models.BinaryField()
    content_type = models.CharField(max_length=40)
    size = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'promotions_bannerimage'

    def __str__(self) -> str:
        return f'Banner image #{self.pk} ({self.content_type}, {self.size} bytes)'
