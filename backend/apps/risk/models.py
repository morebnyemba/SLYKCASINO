"""risk schema — fraud signals, each player's risk state, and review cases.

Players are referenced by ID (no cross-app FK), like every other domain.
"""
from django.db import models


class RiskSettings(models.Model):
    """Operator thresholds for the risk engine (one row)."""
    # Score (sum of recent signal points) at which a player is put under
    # review: new withdrawals are held for staff, bonuses stop.
    review_score = models.PositiveIntegerField(default=40)
    # Score at which the account is suspended automatically. Any critical
    # signal suspends on its own.
    suspend_score = models.PositiveIntegerField(default=100)
    # Signals older than this stop counting towards the score.
    window_days = models.PositiveIntegerField(default=30)
    # More accounts than this signing up from one IP within the window is
    # flagged. Mobile carriers share IPs, so this is only ever a low signal.
    signup_ip_accounts = models.PositiveIntegerField(default=3)
    # A stake at least this big within `new_account_hours` of signing up.
    big_bet_amount = models.DecimalField(max_digits=12, decimal_places=2, default=100)
    new_account_hours = models.PositiveIntegerField(default=24)
    # Deposits over this in 24 hours.
    deposit_volume_24h = models.DecimalField(max_digits=12, decimal_places=2, default=1000)
    # A withdrawal within this many hours of a bonus credit.
    withdraw_after_bonus_hours = models.PositiveIntegerField(default=24)
    # This many different payout numbers on withdrawals within 7 days.
    payout_numbers_7d = models.PositiveIntegerField(default=3)
    # Net winnings (profit credited) over 7 days above this.
    winnings_7d = models.DecimalField(max_digits=12, decimal_places=2, default=1000)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'risk_settings'

    @classmethod
    def load(cls) -> 'RiskSettings':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class RiskProfile(models.Model):
    """A player's current risk state. Flags are set by the engine or staff and
    cleared only by a superuser's review decision."""
    player_id = models.BigIntegerField(unique=True)
    score = models.PositiveIntegerField(default=0)
    # New withdrawal requests are held for staff review.
    under_review = models.BooleanField(default=False)
    # No withdrawals at all (requests are refused).
    withdrawals_frozen = models.BooleanField(default=False)
    # No new bonuses are credited.
    bonus_blocked = models.BooleanField(default=False)
    # Signals before this were reviewed and no longer count.
    cleared_at = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'risk_profile'


class RiskSignal(models.Model):
    """One suspicious thing seen about a player. Never edited; `dedupe_key`
    keeps the same finding from being recorded twice."""

    class Severity(models.TextChoices):
        LOW = 'low', 'Low'
        MEDIUM = 'medium', 'Medium'
        HIGH = 'high', 'High'
        CRITICAL = 'critical', 'Critical'

    POINTS = {Severity.LOW: 10, Severity.MEDIUM: 25, Severity.HIGH: 50, Severity.CRITICAL: 100}

    player_id = models.BigIntegerField(db_index=True)
    code = models.CharField(max_length=40, db_index=True)
    severity = models.CharField(max_length=10, choices=Severity.choices)
    points = models.PositiveIntegerField()
    detail = models.CharField(max_length=300)
    data = models.JSONField(default=dict, blank=True)
    # Other players this finding ties the player to.
    linked_player_ids = models.JSONField(default=list, blank=True)
    dedupe_key = models.CharField(max_length=200, unique=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'risk_signal'
        ordering = ['-created_at']


class RiskCase(models.Model):
    """A player put in front of staff by the engine. One open case per player;
    new signals join it. A superuser closes it: dismissed (flags cleared,
    account reinstated) or confirmed (restrictions stay)."""

    class Status(models.TextChoices):
        OPEN = 'open', 'Open'
        CONFIRMED = 'confirmed', 'Confirmed fraud'
        DISMISSED = 'dismissed', 'Dismissed'

    class Action(models.TextChoices):
        REVIEW = 'review', 'Held for review'
        SUSPENDED = 'suspended', 'Suspended automatically'

    player_id = models.BigIntegerField(db_index=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    action = models.CharField(max_length=10, choices=Action.choices)
    reason = models.CharField(max_length=300)
    score = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)
    decided_at = models.DateTimeField(null=True, blank=True)
    decided_by = models.CharField(max_length=150, blank=True)
    decision_note = models.CharField(max_length=500, blank=True)

    class Meta:
        db_table = 'risk_case'
        ordering = ['-created_at']
        constraints = [
            models.UniqueConstraint(fields=['player_id'], condition=models.Q(status='open'),
                                    name='risk_one_open_case_per_player'),
        ]
