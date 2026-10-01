from django.conf import settings
from django.db import models


class Player(models.Model):
    """A casino player identity. Money lives in the `wallet` app, not here —
    balance is derived from the wallet ledger via wallet.services."""

    class Kyc(models.TextChoices):
        UNVERIFIED = 'unverified', 'Unverified'
        PENDING = 'pending', 'Pending'
        VERIFIED = 'verified', 'Verified'

    class LoyaltyTier(models.TextChoices):
        BRONZE = 'bronze', 'Bronze'
        SILVER = 'silver', 'Silver'
        GOLD = 'gold', 'Gold'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='player',
    )
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(blank=True)
    kyc_status = models.CharField(max_length=20, choices=Kyc.choices, default=Kyc.UNVERIFIED)
    kyc_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    avatar_url = models.CharField(max_length=500, blank=True)
    loyalty_tier = models.CharField(max_length=20, choices=LoyaltyTier.choices, default=LoyaltyTier.BRONZE)

    # --- Responsible gambling ---
    deposit_limit_daily = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
    )
    self_excluded = models.BooleanField(default=False)
    exclusion_ends_at = models.DateTimeField(null=True, blank=True)

    # --- Email verification ---
    email_verified = models.BooleanField(default=False)
    email_verify_token = models.CharField(max_length=64, blank=True, default='')

    # --- Suspension (admin override, hard freeze) ---
    is_suspended = models.BooleanField(default=False)
    suspended_reason = models.CharField(max_length=255, blank=True, default='')
    suspended_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'accounts_player'
        ordering = ['username']

    def __str__(self) -> str:
        return self.username
