from django.db import models


class Team(models.Model):
    """A team/club, sourced from an external provider (e.g. api-football)."""

    name = models.CharField(max_length=200)
    logo_url = models.URLField(blank=True, default='')
    provider = models.CharField(max_length=20, default='', blank=True)
    external_id = models.CharField(max_length=32, null=True, blank=True, db_index=True)

    class Meta:
        db_table = 'sportsbook_team'
        ordering = ['name']
        constraints = [
            models.UniqueConstraint(
                fields=['provider', 'external_id'], name='unique_team_provider_external_id',
            ),
        ]

    def __str__(self) -> str:
        return self.name
