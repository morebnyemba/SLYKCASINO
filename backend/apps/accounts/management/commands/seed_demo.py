"""seed_demo — idempotent demo data seeder."""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone


class Command(BaseCommand):
    help = 'Seed demo casino games, sportsbook events, and promotions (idempotent).'

    def handle(self, *args, **options):
        self._seed_games()
        self._seed_events()
        self._seed_promotions()
        self._seed_tournaments()

    def _seed_games(self):
        from apps.casino.models import Game
        games = [
            {'slug': 'slyk-aviator',      'name': 'SLYK Aviator',      'provider': 'slyk', 'category': 'crash',   'rtp': 99.0,  'is_active': True},
            {'slug': 'lucky-slots',       'name': 'Lucky Slots',       'provider': 'slyk', 'category': 'slots',   'rtp': 96.0,  'is_active': True},
            {'slug': 'golden-wheel',      'name': 'Golden Wheel',      'provider': 'slyk', 'category': 'slots',   'rtp': 97.5,  'is_active': True},
            {'slug': 'mega-dice',         'name': 'Mega Dice',         'provider': 'slyk', 'category': 'instant', 'rtp': 98.0,  'is_active': True},
            {'slug': 'blackjack-classic', 'name': 'Blackjack Classic', 'provider': 'slyk', 'category': 'table',   'rtp': 99.5,  'is_active': True},
            {'slug': 'roulette-pro',      'name': 'Roulette Pro',      'provider': 'slyk', 'category': 'table',   'rtp': 97.3,  'is_active': True},
            {'slug': 'live-baccarat',     'name': 'Live Baccarat',     'provider': 'slyk', 'category': 'live',    'rtp': 98.9,  'is_active': True},
            {'slug': 'virtual-league',    'name': 'Virtual League',    'provider': 'slyk', 'category': 'virtual', 'rtp': 95.0,  'is_active': True},
        ]
        for data in games:
            obj, created = Game.objects.get_or_create(slug=data['slug'], defaults=data)
            if not created and not obj.category:
                obj.category = data['category']
                obj.save(update_fields=['category'])
            label = 'Created' if created else 'Found'
            self.stdout.write(f'  [{label}] Game: {obj.name}')

    def _seed_events(self):
        from apps.sportsbook.models import Event
        events = [
            {'name': 'Man Utd vs Arsenal', 'odds': 1.95, 'featured': True,  'is_open': True, 'starts_at': timezone.now() + timedelta(days=1)},
            {'name': 'Lakers vs Warriors', 'odds': 2.10, 'featured': True,  'is_open': True, 'starts_at': timezone.now() + timedelta(days=2)},
            {'name': 'Federer vs Nadal',   'odds': 1.75, 'featured': False, 'is_open': True, 'starts_at': timezone.now() + timedelta(days=3)},
        ]
        for data in events:
            obj, created = Event.objects.get_or_create(name=data['name'], defaults=data)
            label = 'Created' if created else 'Found'
            self.stdout.write(f'  [{label}] Event: {obj.name}')

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
                'description': 'Wager on SLYK Aviator and the casino this week to climb the leaderboard. Top 10 share the prize pool.',
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
