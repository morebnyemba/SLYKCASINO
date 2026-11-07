from decimal import Decimal

from django.db import models


class CashoutSettings(models.Model):
    """Operator controls for cash-out (one row, edited in the admin console)."""
    enabled = models.BooleanField(default=True)
    allow_partial = models.BooleanField(default=True)
    in_play = models.BooleanField(default=True, help_text='Offer cash-out while matches are being played.')
    # Taken off the fair value of the ticket at current prices.
    margin_percent = models.DecimalField(max_digits=5, decimal_places=2, default=5)
    # Offers below this are not shown, and partial cash-outs can't go below it.
    min_amount = models.DecimalField(max_digits=10, decimal_places=2, default=1)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sportsbook_cashout_settings'

    @classmethod
    def load(cls) -> 'CashoutSettings':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj


class LiveTradingSettings(models.Model):
    """Operator controls for in-play markets (one row). See live_guard.

    The operator's rule: in-play betting stays open from kick-off until the
    75th minute of every live match, when all its markets lock for good.
    Every other automatic hold is OFF by default (markets stay open unless the
    feed or staff suspend them); each can be switched on here."""
    # In-play betting on a match closes for good at this match minute (0 = never).
    lock_minute = models.PositiveSmallIntegerField(default=75)
    # A match-result price moving at least this much in one update with no goal
    # suspends the match for review (0 = off).
    price_jump_percent = models.PositiveSmallIntegerField(default=0)
    # More than this staked in play on one selection within `burst_minutes`
    # suspends the match for review (0 = off).
    burst_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    burst_minutes = models.PositiveSmallIntegerField(default=5)
    # Suspend when the feed's score goes down or its clock runs backwards.
    hold_on_bad_feed = models.BooleanField(default=False)
    # The feed pauses a match for a few seconds many times a game (a dangerous
    # attack, a VAR check). Off (default): its markets stay open at the last
    # prices, and in-play bets placed meanwhile wait until the feed resumes and
    # are then accepted only if the price held and no goal went in. On: every
    # pause suspends the match's markets (the old behaviour).
    suspend_on_feed_pause = models.BooleanField(default=False)
    # The operator's rule: every market on every upcoming and live match stays
    # open until the lock minute, then everything locks. While on, nothing
    # suspends a market by itself — not a feed pause, a market the feed stops
    # offering, a quiet feed, or the automatic holds above; markets keep their
    # last price. Only what play has already decided (an "over" the score has
    # passed, a first-half market once the half is over) and what staff close
    # by hand stay shut.
    keep_markets_open = models.BooleanField(default=True)
    # No in-play bets on a price this short: a selection at 1.01–1.04 is as good
    # as won already (and pads a multiple at no risk). Applies to every in-play
    # pick, single or in a multiple; 0 = off. Pre-match prices are unaffected.
    live_min_odds = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal('1.05'))
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'sportsbook_live_trading_settings'

    CACHE_KEY = 'sportsbook:live-trading-settings'

    @classmethod
    def load(cls) -> 'LiveTradingSettings':
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @classmethod
    def current(cls) -> 'LiveTradingSettings':
        """load() for hot paths (every event on a board): cached for a few
        seconds and dropped whenever the settings are saved."""
        from django.core.cache import cache
        obj = cache.get(cls.CACHE_KEY)
        if obj is None:
            obj = cls.load()
            cache.set(cls.CACHE_KEY, obj, 5)
        return obj

    def save(self, *args, **kwargs):
        from django.core.cache import cache
        super().save(*args, **kwargs)
        cache.delete(self.CACHE_KEY)


class Cashout(models.Model):
    """One cash-out taken on a single bet or an accumulator slip. Its id keys
    the wallet credit, so a retried request can never pay twice."""
    bet = models.ForeignKey('Bet', null=True, blank=True, on_delete=models.CASCADE, related_name='cashouts')
    slip = models.ForeignKey('BetSlip', null=True, blank=True, on_delete=models.CASCADE, related_name='cashouts')
    player_id = models.BigIntegerField(db_index=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    stake_portion = models.DecimalField(max_digits=12, decimal_places=2)
    full = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'sportsbook_cashout'
        ordering = ['-created_at']

    def __str__(self) -> str:
        target = f'bet {self.bet_id}' if self.bet_id else f'slip {self.slip_id}'
        return f'Cash-out {self.amount} on {target}'
