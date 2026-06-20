from django.db import models
from django.utils import timezone


class Tournament(models.Model):
    """A leaderboard competition (e.g. "Aviator Weekly Race"). Players opt in,
    then accumulate `score` from their wagering while the tournament is live."""

    class Metric(models.TextChoices):
        WAGERED = 'wagered', 'Total wagered'

    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    metric = models.CharField(max_length=20, choices=Metric.choices, default=Metric.WAGERED)
    prize_pool = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    currency = models.CharField(max_length=8, default='USD')
    active = models.BooleanField(default=True)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'promotions_tournament'
        ordering = ['-active', '-ends_at']

    def __str__(self) -> str:
        return self.name

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


class TournamentEntry(models.Model):
    """A player's standing in a tournament. `player_name` is denormalized so the
    public leaderboard renders without touching the accounts context."""

    tournament = models.ForeignKey('promotions.Tournament', on_delete=models.CASCADE, related_name='entries')
    player_id = models.BigIntegerField(db_index=True)
    player_name = models.CharField(max_length=150, blank=True)
    score = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'promotions_tournament_entry'
        ordering = ['-score', 'updated_at']
        constraints = [
            models.UniqueConstraint(fields=['tournament', 'player_id'], name='uniq_tournament_player'),
        ]

    def __str__(self) -> str:
        return f'entry(t={self.tournament_id}, player={self.player_id}, {self.score})'
