"""Reopen every market on every upcoming and live match (see sportsbook.unlock)."""
from django.core.management.base import BaseCommand

from apps.sportsbook import live_guard
from apps.sportsbook.models import Event, LiveTradingSettings, Market, MarketOutcome
from apps.sportsbook.unlock import unlock_markets


class Command(BaseCommand):
    help = 'Reopen every market and betting option on every upcoming and live match (not past the lock minute).'

    def handle(self, *args, **options):
        report = unlock_markets(
            Event=Event, Market=Market, MarketOutcome=MarketOutcome,
            lock_minute=LiveTradingSettings.load().lock_minute, after_live=live_guard.close_decided,
        )
        self.stdout.write(self.style.SUCCESS(
            f"Reopened {report['markets']} markets and {report['outcomes']} outcomes; "
            f"{report['events']} matches reopened, {report['holds_cleared']} holds cleared."))
