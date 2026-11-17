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


class FeedQuotaDay(models.Model):
    """One provider's API request quota for one day (the provider's day: UTC).
    `used` counts the requests this app made; `limit`/`remaining` are what the
    provider last reported in its response headers (the source of truth: it
    includes requests made from anywhere with the same key)."""

    provider = models.CharField(max_length=20)
    day = models.DateField()
    used = models.PositiveIntegerField(default=0)
    limit = models.PositiveIntegerField(null=True, blank=True)
    remaining = models.IntegerField(null=True, blank=True)
    remaining_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'sportsbook_feed_quota_day'
        constraints = [models.UniqueConstraint(fields=['provider', 'day'], name='feed_quota_one_row_per_day')]


class FeedJob(models.Model):
    """The feed manager's state for one kind of fetch (live odds, live scores,
    pre-match odds, imports, settlement…): when it last ran, what a run costs
    on average (requests), and today's counts. See sportsbook.feed_manager."""

    kind = models.CharField(max_length=30, unique=True)
    last_run_at = models.DateTimeField(null=True, blank=True)
    cost = models.FloatField(default=1.0)
    day = models.DateField(null=True, blank=True)
    runs_today = models.PositiveIntegerField(default=0)
    skipped_today = models.PositiveIntegerField(default=0)
    requests_today = models.PositiveIntegerField(default=0)
    # The interval the manager last planned for this kind (seconds).
    planned_interval = models.FloatField(null=True, blank=True)

    class Meta:
        db_table = 'sportsbook_feed_job'
