from decimal import Decimal

from django.db import models


class PromoCode(models.Model):
    """A code players enter when depositing to get a bonus (into their Bonus
    wallet). Created, edited and deactivated by staff; see promo_codes.py."""

    class Kind(models.TextChoices):
        PERCENT = 'percent', 'Percent of the deposit'
        FIXED = 'fixed', 'Fixed bonus'

    # Stored upper-case; players can type it in any case.
    code = models.CharField(max_length=40, unique=True)
    name = models.CharField(max_length=120)
    description = models.CharField(max_length=300, blank=True)
    active = models.BooleanField(default=True)
    kind = models.CharField(max_length=10, choices=Kind.choices, default=Kind.PERCENT)
    # Percent (e.g. 100 = 100%) or a fixed amount, by kind.
    value = models.DecimalField(max_digits=12, decimal_places=2)
    # Most a percent code can give on one deposit (0 = no cap).
    max_bonus = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('0'))
    min_deposit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('1'))
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    # Total redemptions across all players (0 = unlimited).
    max_uses = models.PositiveIntegerField(default=0)
    # Redemptions per player (0 = unlimited).
    per_player_limit = models.PositiveIntegerField(default=1)
    created_by = models.CharField(max_length=150, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'promotions_promo_code'
        ordering = ['-created_at']

    def __str__(self) -> str:
        return self.code


class PromoRedemption(models.Model):
    """One use of a promo code on one deposit. Unique per deposit, so a
    redelivered payment callback can never pay the bonus twice."""
    promo = models.ForeignKey(PromoCode, on_delete=models.PROTECT, related_name='redemptions')
    player_id = models.BigIntegerField(db_index=True)
    deposit_entry_id = models.BigIntegerField(unique=True)
    deposit_amount = models.DecimalField(max_digits=12, decimal_places=2)
    bonus_amount = models.DecimalField(max_digits=12, decimal_places=2)
    # False when the fraud engine refused the bonus (the use still counts).
    credited = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'promotions_promo_redemption'
        ordering = ['-created_at']
