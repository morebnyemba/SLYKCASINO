from django.db import models


class PromotionClaim(models.Model):
    """A player's claim on a promotion. `player_id` references accounts.Player by
    ID. Tracks wagering progress toward the requirement before bonus unlock."""

    class Status(models.TextChoices):
        ACTIVE = 'active', 'Active'
        COMPLETED = 'completed', 'Completed'
        EXPIRED = 'expired', 'Expired'
        FORFEITED = 'forfeited', 'Forfeited'

    player_id = models.BigIntegerField(db_index=True)
    promotion = models.ForeignKey('promotions.Promotion', on_delete=models.PROTECT, related_name='claims')
    bonus_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    wagering_required = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    wagering_progress = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ACTIVE)
    bonus_credited = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'promotions_claim'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['player_id', 'promotion'], name='uniq_player_promotion_claim'),
        ]

    def __str__(self) -> str:
        return f'claim(player={self.player_id}, promo={self.promotion_id}, {self.status})'
