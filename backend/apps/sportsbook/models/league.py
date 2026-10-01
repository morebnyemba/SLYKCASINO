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
    # Display: matches are grouped under their league in the sportsbook.
    country = models.CharField(max_length=100, blank=True, default='')
    logo_url = models.URLField(max_length=500, blank=True, default='')
    flag_url = models.URLField(max_length=500, blank=True, default='')
    # Lower shows first; the big competitions are seeded with low numbers and
    # everything else follows alphabetically. Editable in Django admin.
    sort_order = models.PositiveIntegerField(default=1000)

    class Meta:
        db_table = 'sportsbook_league_setting'
        ordering = ['sort_order', 'name']
        constraints = [
            models.UniqueConstraint(fields=['provider', 'league_id'], name='unique_league_setting'),
        ]

    def __str__(self) -> str:
        return self.name or f'League {self.league_id}'


# api-football league ids shown first, in this order (sort_order = position).
FEATURED_LEAGUES = (
    2,    # UEFA Champions League
    39,   # Premier League
    140,  # La Liga
    135,  # Serie A
    78,   # Bundesliga
    61,   # Ligue 1
    3,    # UEFA Europa League
    848,  # UEFA Conference League
    1,    # World Cup
    4,    # Euro Championship
    94,   # Primeira Liga
    88,   # Eredivisie
    203,  # Super Lig
    253,  # MLS
    71,   # Brasileirao Serie A
    288,  # South Africa Premier Soccer League
)


def featured_sort_order(league_id: int) -> int:
    try:
        return (FEATURED_LEAGUES.index(int(league_id)) + 1) * 10
    except ValueError:
        return 1000
