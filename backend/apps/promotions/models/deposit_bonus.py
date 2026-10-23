from django.db import models


class DepositBonus(models.Model):
    """A deposit promotion tier: a deposit between `min_deposit` and
    `max_deposit` (inclusive; no max = and above) earns `percent` of it as
    bonus money, capped at `max_bonus` (0 = no cap), which must be wagered
    `wagering_multiplier` times before it can be withdrawn. When several tiers
    match a deposit, the one giving the biggest bonus wins (one per deposit)."""

    class Limit(models.TextChoices):
        EVERY = 'every', 'Every deposit'
        DAILY = 'daily', 'Once a day'
        ONCE = 'once', 'Once per player'

    name = models.CharField(max_length=80)
    active = models.BooleanField(default=True)
    min_deposit = models.DecimalField(max_digits=12, decimal_places=2)
    max_deposit = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    percent = models.DecimalField(max_digits=6, decimal_places=2)
    max_bonus = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    wagering_multiplier = models.DecimalField(max_digits=5, decimal_places=2, default=5)
    limit = models.CharField(max_length=10, choices=Limit.choices, default=Limit.EVERY)
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'promotions_deposit_bonus'
        ordering = ['min_deposit', 'pk']

    def __str__(self) -> str:
        return f'{self.name} ({self.percent}% from {self.min_deposit})'
