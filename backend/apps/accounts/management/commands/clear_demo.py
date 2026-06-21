"""clear_demo — removes exactly the records seed_demo creates (idempotent, safe to re-run)."""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Delete demo casino games, sportsbook events, promotions, tournaments, and banners seeded by seed_demo.'

    def handle(self, *args, **options):
        self._clear_games()
        self._clear_events()
        self._clear_promotions()
        self._clear_tournaments()
        self._clear_banners()

    def _clear_games(self):
        from apps.casino.models import Game
        slugs = [
            'slyk-aviator', 'lucky-slots', 'golden-wheel', 'mega-dice',
            'blackjack-classic', 'roulette-pro', 'live-baccarat', 'virtual-league',
        ]
        deleted, _ = Game.objects.filter(slug__in=slugs).delete()
        self.stdout.write(f'  Deleted {deleted} demo game row(s)')

    def _clear_events(self):
        from apps.sportsbook.models import Event
        names = ['Man Utd vs Arsenal', 'Lakers vs Warriors', 'Federer vs Nadal']
        # provider='' excludes anything synced from api-football, even if a name collides.
        deleted, _ = Event.objects.filter(name__in=names, provider='').delete()
        self.stdout.write(f'  Deleted {deleted} demo event row(s)')

    def _clear_promotions(self):
        from apps.promotions.models import Promotion
        names = ['Welcome Bonus', 'Free Bet Friday', 'Weekend Cashback']
        deleted, _ = Promotion.objects.filter(name__in=names).delete()
        self.stdout.write(f'  Deleted {deleted} demo promotion row(s)')

    def _clear_tournaments(self):
        from apps.promotions.models import Tournament
        names = ['Aviator Weekly Race', 'Slots Jackpot Race']
        deleted, _ = Tournament.objects.filter(name__in=names).delete()
        self.stdout.write(f'  Deleted {deleted} demo tournament row(s)')

    def _clear_banners(self):
        from apps.promotions.models import Banner
        titles = ['SLYK Aviator', 'Welcome Bonus', 'Weekly Tournaments']
        deleted, _ = Banner.objects.filter(title__in=titles).delete()
        self.stdout.write(f'  Deleted {deleted} demo banner row(s)')
