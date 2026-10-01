from django.db import models


class CrashRound(models.Model):
    """A single Aviator-style crash bet (provably fair, single-player).

    The crash point is committed up-front via `server_seed_hash` (revealed only
    after the round settles, so the player can verify it wasn't changed). The
    rising multiplier is a deterministic function of elapsed time since
    `created_at`; the server is authoritative on cash-out, never the client.

    Lifecycle: RUNNING -> CASHED (player cashed out below the crash point) /
    BUSTED (crash reached before cash-out)."""

    class Status(models.TextChoices):
        RUNNING = 'running', 'Running'
        CASHED = 'cashed', 'Cashed out'
        BUSTED = 'busted', 'Busted'

    player_id = models.BigIntegerField(db_index=True)
    stake = models.DecimalField(max_digits=12, decimal_places=2)
    crash_point = models.DecimalField(max_digits=10, decimal_places=2)
    cashout_multiplier = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    win = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.RUNNING)
    debit_confirmed = models.BooleanField(default=False)
    server_seed = models.CharField(max_length=80)
    server_seed_hash = models.CharField(max_length=80)
    nonce = models.BigIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'casino_crash_round'
        ordering = ['-created_at']
        indexes = [models.Index(fields=['status', 'created_at'])]

    def __str__(self) -> str:
        return f'crash(player={self.player_id}, x{self.crash_point}, {self.status})'
