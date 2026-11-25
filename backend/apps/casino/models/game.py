from django.db import models


class Game(models.Model):
    """A casino game in the catalog (provider-backed)."""

    class Category(models.TextChoices):
        SLOTS = 'slots', 'Slots'
        CRASH = 'crash', 'Crash'
        FAST = 'fast', 'Fast Games'
        MINI = 'mini', 'Mini Games'
        LIVE = 'live', 'Live Casino'
        TABLE = 'table', 'Table Games'
        VIRTUAL = 'virtual', 'Virtual Sports'
        INSTANT = 'instant', 'Instant Win'

    slug = models.SlugField(max_length=120, unique=True)
    name = models.CharField(max_length=200)
    provider = models.CharField(max_length=80, default='stub')
    category = models.CharField(max_length=20, choices=Category.choices, default=Category.SLOTS, db_index=True)
    rtp = models.DecimalField(max_digits=5, decimal_places=2, default=96.0)  # %
    is_active = models.BooleanField(default=True)
    image_url = models.CharField(max_length=500, blank=True)
    # Listed but not playable yet: the lobby shows "Coming soon" and players can ask to be
    # told when it's ready (GameWaitlist). Switching it off notifies them (services.launch).
    coming_soon = models.BooleanField(default=False, db_index=True)

    class Meta:
        db_table = 'casino_game'
        ordering = ['name']

    def __str__(self) -> str:
        return self.name


class GameWaitlist(models.Model):
    """A player who asked to be told when a coming-soon game is ready."""
    game = models.ForeignKey(Game, on_delete=models.CASCADE, related_name='waitlist')
    player_id = models.BigIntegerField(db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    notified_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'casino_game_waitlist'
        constraints = [models.UniqueConstraint(fields=['game', 'player_id'], name='casino_waitlist_once')]
