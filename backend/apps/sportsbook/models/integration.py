from django.db import models


class ProviderCredential(models.Model):
    """An API key/base URL for an external provider, editable from Django
    admin so ops can rotate or set a key without a redeploy. Falls back to
    the env-var settings (API_FOOTBALL_KEY/...) when no row exists or the
    row's fields are blank — see clients.ApiFootballClient.__init__."""

    provider = models.CharField(max_length=20, unique=True)
    api_key = models.CharField(max_length=200, blank=True, default='')
    base_url = models.URLField(blank=True, default='')

    class Meta:
        db_table = 'sportsbook_provider_credential'

    def __str__(self) -> str:
        return self.provider
