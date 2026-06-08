from django.conf import settings
from django.db import models


class Player(models.Model):
    """A casino player identity. Money lives in the `wallet` app, not here —
    balance is derived from the wallet ledger via wallet.services."""

    class Kyc(models.TextChoices):
        UNVERIFIED = 'unverified', 'Unverified'
        PENDING = 'pending', 'Pending'
        VERIFIED = 'verified', 'Verified'

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='player',
    )
    username = models.CharField(max_length=150, unique=True)
    email = models.EmailField(blank=True)
    kyc_status = models.CharField(max_length=20, choices=Kyc.choices, default=Kyc.UNVERIFIED)
    kyc_updated_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    # --- Responsible gambling ---
    # Daily deposit limit in the player's wallet currency. None = no limit set.
    deposit_limit_daily = models.DecimalField(
        max_digits=12, decimal_places=2, null=True, blank=True,
    )
    # Cooling-off / self-exclusion. While self_excluded=True the account cannot
    # deposit, bet, or spin. exclusion_ends_at=None means indefinite exclusion.
    self_excluded = models.BooleanField(default=False)
    exclusion_ends_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'accounts_player'
        ordering = ['username']

    def __str__(self) -> str:
        return self.username
