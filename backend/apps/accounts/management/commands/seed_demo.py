"""seed_demo — idempotent demo data seeder."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Seed the Aviator catalogue entry, demo promotions, tournaments and banners (idempotent). Matches come from the live feed only.'

    def handle(self, *args, **options):
        self._rebrand_legacy_demo()
        self._seed_games()
        self._seed_promotions()
        self._seed_tournaments()
        self._seed_banners()

    def _rebrand_legacy_demo(self):
        """Rows seeded before the SLYK -> BetBlits rebrand: rename them in place
        (get_or_create below only applies new values when it creates a row)."""
        from apps.casino.models import Game
        from apps.promotions.models import Banner, Tournament
        old, new = 'SLYK Aviator', 'BetBlits Aviator'
        renamed = Game.objects.filter(name=old).update(name=new)
        if not Banner.objects.filter(title=new).exists():
            renamed += Banner.objects.filter(title=old).update(title=new)
        for t in Tournament.objects.filter(description__contains=old):
            t.description = t.description.replace(old, new)
            t.save(update_fields=['description'])
            renamed += 1
        if renamed:
            self.stdout.write(f'  Renamed {renamed} legacy SLYK demo row(s)')

    def _seed_games(self):
        from apps.casino.models import Game
        # Only the in-house Aviator crash game; the placeholder demo games
        # (slots, table, live…) were retired — see casino migration 0004.
        games = [
            {'slug': 'slyk-aviator', 'name': 'BetBlits Aviator', 'provider': 'slyk', 'category': 'crash', 'rtp': 99.0, 'is_active': True},
        ]
        for data in games:
            obj, created = Game.objects.get_or_create(slug=data['slug'], defaults=data)
            if not created and not obj.category:
                obj.category = data['category']
                obj.save(update_fields=['category'])
            label = 'Created' if created else 'Found'
            self.stdout.write(f'  [{label}] Game: {obj.name}')

    def _seed_promotions(self):
        from apps.promotions.models import Promotion
        promotions = [
            {'name': 'Welcome Bonus',     'kind': 'deposit',  'bonus_amount': 100, 'wagering_multiplier': 20, 'active': True},
            {'name': 'Free Bet Friday',   'kind': 'freebet',  'bonus_amount': 10,  'wagering_multiplier': 5,  'active': True},
            {'name': 'Weekend Cashback',  'kind': 'cashback', 'bonus_amount': 25,  'wagering_multiplier': 3,  'active': True},
        ]
        for data in promotions:
            obj, created = Promotion.objects.get_or_create(name=data['name'], defaults=data)
            label = 'Created' if created else 'Found'
            self.stdout.write(f'  [{label}] Promotion: {obj.name}')

    def _seed_tournaments(self):
        from apps.promotions.models import Tournament
        tournaments = [
            {
                'name': 'Aviator Weekly Race',
                'description': 'Wager on BetBlits Aviator and the casino this week to climb the leaderboard. Top 10 share the prize pool.',
                'metric': 'wagered', 'prize_pool': 500, 'currency': 'USD', 'active': True,
                'starts_at': timezone.now() - timedelta(days=1),
                'ends_at': timezone.now() + timedelta(days=6),
            },
            {
                'name': 'Slots Jackpot Race',
                'description': 'Every spin counts. Race other players for the monthly jackpot prize pool.',
                'metric': 'wagered', 'prize_pool': 1000, 'currency': 'USD', 'active': True,
                'starts_at': timezone.now() - timedelta(days=2),
                'ends_at': timezone.now() + timedelta(days=20),
            },
        ]
        for data in tournaments:
            obj, created = Tournament.objects.get_or_create(name=data['name'], defaults=data)
            label = 'Created' if created else 'Found'
            self.stdout.write(f'  [{label}] Tournament: {obj.name}')

    def _seed_banners(self):
        from apps.promotions.models import Banner
        base = 'https://images.unsplash.com'
        banners = [
            {
                'title': 'BetBlits Aviator', 'subtitle': 'Cash out before the crash — win up to 100×',
                'image_url': f'{base}/photo-1606167668584-78701c57f13d?w=1600&q=80&auto=format',
                'link_url': '/casino/crash', 'cta_label': 'Play now', 'sort_order': 1,
            },
            {
                'title': 'Welcome Bonus', 'subtitle': 'Claim your 100% deposit match and start winning',
                'image_url': f'{base}/photo-1596731498067-93a4b7174c93?w=1600&q=80&auto=format',
                'link_url': '/promotions', 'cta_label': 'Claim bonus', 'sort_order': 2,
            },
            {
                'title': 'Weekly Tournaments', 'subtitle': 'Climb the leaderboard and share the prize pool',
                'image_url': f'{base}/photo-1518895949257-7621c3c786d7?w=1600&q=80&auto=format',
                'link_url': '/tournaments', 'cta_label': 'View races', 'sort_order': 3,
            },
        ]
        for data in banners:
            obj, created = Banner.objects.get_or_create(title=data['title'], defaults=data)
            label = 'Created' if created else 'Found'
            self.stdout.write(f'  [{label}] Banner: {obj.title}')
