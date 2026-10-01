from django.db import models


class LeagueSetting(models.Model):
    """A league api-football has offered, recorded the first time auto-import
    discovers it. Enabled by default so "all leagues" sync works with zero
    config; an operator disables specific ones from Django admin instead of
    curating an opt-in allowlist by hand. Disabled leagues are skipped
    before their /fixtures call is made (see services.import_all_current_leagues),
    so disabling one also saves API quota, not just sportsbook clutter."""

    provider = models.CharField(max_length=20, default='api-football')
    league_id = models.PositiveIntegerField()
    name = models.CharField(max_length=200, blank=True, default='')
    enabled = models.BooleanField(default=True)

    class Meta:
        db_table = 'sportsbook_league_setting'
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(fields=['provider', 'league_id'], name='unique_league_setting'),
        ]

    def __str__(self) -> str:
        return self.name or f'League {self.league_id}'
