"""Jet — a multiplayer crash game. Everyone flies the same round: bets are
taken during a short countdown, then the multiplier climbs until the round's
pre-committed crash point. A bet pays stake x the multiplier it was cashed out
at; one still riding at the crash loses.

Fairness: each round's crash point comes from a secret server seed whose
SHA-256 hash is published before any bet is taken and the seed itself after the
crash (see engine.crash_point). There are no automated players and no way to
set a crash point by hand.
"""
from decimal import Decimal

from django.db import models


class JetSettings(models.Model):
    """Operator settings (one row). Every limit here is shown to players."""
    enabled = models.BooleanField(default=True)
    # The game's name as players see it (header, menus, page title).
    display_name = models.CharField(max_length=40, default='BetBlits Aviator')
    house_edge_percent = models.DecimalField(max_digits=4, decimal_places=2, default=Decimal('3.00'))
    min_bet = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('0.10'))
    max_bet = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('100.00'))
    # Most a single bet can pay; a bet that reaches it is cashed out there.
    max_win = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('10000.00'))
    # Highest multiplier a round can reach.
    max_multiplier = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('1000.00'))
    # Total stakes one round accepts; later bets are refused ("round full").
    round_stake_limit = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('5000.00'))
    betting_seconds = models.PositiveSmallIntegerField(default=6)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = 'jet_settings'
        verbose_name_plural = 'Jet settings'

    @classmethod
    def load(cls) -> 'JetSettings':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class JetRound(models.Model):
    class Status(models.TextChoices):
        BETTING = 'betting', 'Taking bets'
        FLYING = 'flying', 'Flying'
        CRASHED = 'crashed', 'Crashed'

    status = models.CharField(max_length=8, choices=Status.choices, default=Status.BETTING, db_index=True)
    # Secret until the crash; its SHA-256 (seed_hash) is public from the start.
    server_seed = models.CharField(max_length=64)
    seed_hash = models.CharField(max_length=64)
    crash_point = models.DecimalField(max_digits=10, decimal_places=2)
    house_edge_percent = models.DecimalField(max_digits=4, decimal_places=2)
    betting_ends_at = models.DateTimeField()
    started_at = models.DateTimeField(null=True, blank=True)
    crashed_at = models.DateTimeField(null=True, blank=True)
    total_stake = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    total_payout = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    bet_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'jet_round'
        ordering = ['-id']

    def __str__(self) -> str:
        return f'Round {self.id} ({self.status})'


class JetBet(models.Model):
    class Status(models.TextChoices):
        ACTIVE = 'active', 'Riding'
        CASHED = 'cashed', 'Cashed out'
        LOST = 'lost', 'Lost'
        REFUNDED = 'refunded', 'Refunded'

    round = models.ForeignKey(JetRound, on_delete=models.CASCADE, related_name='bets')
    player_id = models.BigIntegerField(db_index=True)
    # Shown in the live bets list, e.g. "t***o".
    display_name = models.CharField(max_length=20)
    slot = models.PositiveSmallIntegerField(default=1)
    stake = models.DecimalField(max_digits=10, decimal_places=2)
    auto_cashout = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.ACTIVE, db_index=True)
    cashout_multiplier = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payout = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    settled_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = 'jet_bet'
        ordering = ['-id']
        constraints = [
            models.UniqueConstraint(fields=['round', 'player_id', 'slot'], name='jet_one_bet_per_slot'),
        ]

    def __str__(self) -> str:
        return f'{self.stake} on round {self.round_id} ({self.status})'
