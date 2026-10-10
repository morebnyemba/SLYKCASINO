"""Jet — a multiplayer crash game. Everyone flies the same round: bets are
taken during a short countdown, then the multiplier climbs until the round's
pre-committed crash point. A bet pays stake x the multiplier it was cashed out
at; one still riding at the crash loses.

Fairness: each round's crash point comes from a secret server seed whose
SHA-256 hash is published before any bet is taken and the seed itself after the
crash (see engine.crash_point). There is no way to set a crash point by hand.
Optional simulated players (bots.py) only appear in the live bets list: they
never stake money, are never stored, and can't affect a round.
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
    # Simulated players in the live bets list (display only, see bots.py).
    bots_enabled = models.BooleanField(default=False)
    bot_count = models.PositiveSmallIntegerField(default=300)
    # Simulated players also say short, neutral things in the chat (see bot_chat.py).
    bot_chat_enabled = models.BooleanField(default=False)
    bot_chat_per_minute = models.PositiveSmallIntegerField(default=3)
    # Chat lobby, and "rain": free bets dropped on active real players.
    chat_enabled = models.BooleanField(default=True)
    rain_enabled = models.BooleanField(default=False)
    rain_amount = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal('1.00'))
    rain_players = models.PositiveSmallIntegerField(default=10)
    # Minutes between automatic rains (0: only when staff press the button).
    rain_every_minutes = models.PositiveSmallIntegerField(default=30)
    # Most the rains may give away per day, in free-bet value.
    rain_daily_budget = models.DecimalField(max_digits=10, decimal_places=2, default=Decimal('50.00'))
    last_rain_at = models.DateTimeField(null=True, blank=True)
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
    # Placed with a free bet: no stake was taken and it's left out of round totals.
    is_free = models.BooleanField(default=False)
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


class JetFreeBet(models.Model):
    """A free bet (e.g. from a chat rain). Placing it costs the player nothing;
    a win pays the winnings only (stake not returned) as a bonus credit, so it
    shows up as a bonus cost in NGR and never as gaming turnover or GGR."""

    class Status(models.TextChoices):
        AVAILABLE = 'available', 'Available'
        USED = 'used', 'Used'
        EXPIRED = 'expired', 'Expired'

    player_id = models.BigIntegerField(db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    source = models.CharField(max_length=20, default='rain')
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.AVAILABLE, db_index=True)
    expires_at = models.DateTimeField()
    bet = models.OneToOneField(JetBet, null=True, blank=True, on_delete=models.SET_NULL, related_name='free_bet')
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'jet_free_bet'
        ordering = ['expires_at', 'id']


class JetChatMessage(models.Model):
    class Kind(models.TextChoices):
        CHAT = 'chat', 'Player message'
        WIN = 'win', 'Big win'
        RAIN = 'rain', 'Rain'
        SYSTEM = 'system', 'Notice'
        BOT = 'bot', 'Simulated player'

    kind = models.CharField(max_length=8, choices=Kind.choices, default=Kind.CHAT)
    # Empty for messages from the game itself (wins, rain, notices).
    player_id = models.BigIntegerField(null=True, blank=True, db_index=True)
    name = models.CharField(max_length=20)
    body = models.CharField(max_length=200)
    hidden = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = 'jet_chat_message'
        ordering = ['-id']


class JetChatMute(models.Model):
    player_id = models.BigIntegerField(unique=True)
    until = models.DateTimeField()
    by = models.CharField(max_length=150, blank=True)

    class Meta:
        db_table = 'jet_chat_mute'
