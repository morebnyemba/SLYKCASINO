"""The Jet round runner: one long-running process that drives every round.

    betting (countdown) -> flying (auto cash-outs paid as the plane passes them)
    -> crashed (seed revealed) -> short pause -> next round

Run exactly one (the `jet` service in docker-compose). Bets and manual
cash-outs don't go through here — the API decides them from the server clock —
so a slow tick never changes who wins.
"""
import logging
import time

from django.core.management.base import BaseCommand
from django.db import close_old_connections
from django.utils import timezone

from apps.jet import bot_chat, bots, services, social
from apps.jet.models import JetSettings

logger = logging.getLogger(__name__)

TICK = 0.2
# When simulated players last had a chance to chat (they speak twice a round).
_last_chat = {'at': None}


def _bot_chat(rnd, phase: str) -> None:
    now = timezone.now()
    seconds = (now - _last_chat['at']).total_seconds() if _last_chat['at'] else 10.0
    _last_chat['at'] = now
    try:
        bot_chat.speak(rnd, phase, min(seconds, 120.0), now=now)
    except Exception:  # noqa: BLE001 — background chatter must never stop the game
        logger.exception('jet bot chat failed')


def run_round() -> None:
    rnd = services.open_round()
    feed = bots.Feed(rnd)  # simulated players: display only, never money
    _bot_chat(rnd, 'betting')
    while timezone.now() < rnd.betting_ends_at:
        feed.tick(timezone.now())
        time.sleep(min(0.5, max(0.0, (rnd.betting_ends_at - timezone.now()).total_seconds())))
    rnd = services.start_flight(rnd.id)
    feed.take_off(rnd)
    crash_at = rnd.started_at + timezone.timedelta(seconds=services.flight_seconds(rnd))
    while timezone.now() < crash_at:
        services.settle_auto_cashouts(rnd.id)
        feed.tick(timezone.now())
        time.sleep(min(TICK, max(0.0, (crash_at - timezone.now()).total_seconds())))
    rnd = services.crash_round(rnd.id)
    feed.rnd = rnd
    feed.tick(timezone.now())  # bots whose target was right at the crash point
    _bot_chat(rnd, 'crashed')
    for extra in (lambda: social.announce_round(rnd), social.maybe_auto_rain, bot_chat.prune):
        try:
            extra()
        except Exception:  # noqa: BLE001 — chat and rain must never stop the game
            logger.exception('jet social step failed')
    time.sleep(services.COOLDOWN_SECONDS)


class Command(BaseCommand):
    help = 'Run the Jet crash-game rounds (one instance only).'

    def handle(self, *args, **options):
        closed = services.recover()
        self.stdout.write(f'Jet runner started ({closed} interrupted round(s) closed).')
        while True:
            close_old_connections()
            try:
                if not JetSettings.load().enabled:
                    services.publish_now({'type': 'paused'})
                    time.sleep(3)
                    continue
                run_round()
            except Exception:  # noqa: BLE001 — keep flying; the next round starts clean
                logger.exception('jet round failed')
                time.sleep(2)
                try:
                    services.recover()
                except Exception:  # noqa: BLE001
                    logger.exception('jet recovery failed')
