from django.db import models

from .tokens import default_dark, default_light


class SiteTheme(models.Model):
    """The single, sitewide color theme. A singleton — always pk=1.

    `light`/`dark` are dicts keyed by the token names in `tokens.TOKEN_KEYS`,
    each a CSS color string. They're injected as CSS custom property
    overrides at request time (see apps/web's root layout), so every
    component that already consumes `var(--primary)` etc. picks up operator
    edits with no code changes.
    """
    light = models.JSONField(default=default_light)
    dark = models.JSONField(default=default_dark)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by_username = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = 'branding_site_theme'

    def __str__(self) -> str:
        return 'Site theme'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> 'SiteTheme':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class SiteIdentity(models.Model):
    """The single, sitewide brand identity. A singleton — always pk=1.

    `logo_url` blank means "no logo image configured" — consumers fall back
    to the default text/icon brand mark rather than rendering a broken <img>.
    """
    site_name = models.CharField(max_length=80, default='BetBlits')
    tagline = models.CharField(max_length=120, blank=True, default='Bet smart. Brag often.')
    logo_url = models.CharField(max_length=500, blank=True)
    license_text = models.TextField(
        blank=True,
        # Blank until the operator enters the licence they hold (Admin → Branding);
        # the site makes no licensing claim while it is empty.
        default='',
    )
    # International format, digits only (e.g. 263771234567). Blank hides the
    # site's WhatsApp support button.
    whatsapp_number = models.CharField(max_length=20, blank=True, default='')
    updated_at = models.DateTimeField(auto_now=True)
    updated_by_username = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = 'branding_site_identity'

    def __str__(self) -> str:
        return self.site_name

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls) -> 'SiteIdentity':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj
