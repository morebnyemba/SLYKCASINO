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
        self._seed_banners()

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
            {
                'name': 'Man Utd vs Arsenal', 'sport': 'football', 'odds': 1.95, 'odds_draw': 3.40,
                'odds_away': 3.80, 'featured': True, 'is_open': True, 'starts_at': timezone.now() + timedelta(days=1),
            },
            {
                'name': 'Lakers vs Warriors', 'sport': 'basketball', 'odds': 2.10,
                'featured': True, 'is_open': True, 'starts_at': timezone.now() + timedelta(days=2),
            },
            {
                'name': 'Federer vs Nadal', 'sport': 'tennis', 'odds': 1.75,
                'featured': False, 'is_open': True, 'starts_at': timezone.now() + timedelta(days=3),
            },
        ]
        for data in events:
            obj, created = Event.objects.get_or_create(name=data['name'], defaults=data)
            label = 'Created' if created else 'Found'
            self.stdout.write(f'  [{label}] Event: {obj.name}')
            if obj.sport == 'football':
                self._seed_markets(obj)

    def _seed_markets(self, event):
        """Give the demo football fixture a full market board, run through the same
        parser + upsert path the api-football odds sync uses."""
        from apps.sportsbook.market_feed import parse_markets
        from apps.sportsbook.services import apply_feed_markets

        def bet(name, *pairs):
            return {'name': name, 'values': [{'value': v, 'odd': o} for v, o in pairs]}

        bets = [
            bet('Double Chance', ('Home/Draw', '1.25'), ('Home/Away', '1.30'), ('Draw/Away', '1.80')),
            bet('Home/Away', ('Home', '1.40'), ('Away', '2.75')),
            bet('Both Teams Score', ('Yes', '1.72'), ('No', '2.05')),
            bet('Goals Over/Under', ('Over 1.5', '1.28'), ('Under 1.5', '3.60'), ('Over 2.5', '1.90'),
                ('Under 2.5', '1.90'), ('Over 3.5', '3.05'), ('Under 3.5', '1.36')),
            bet('Exact Goals Number', ('0', '11.00'), ('1', '5.50'), ('2', '3.70'), ('3', '3.90'),
                ('4', '6.00'), ('more 4', '6.50')),
            bet('Odd/Even', ('Odd', '1.95'), ('Even', '1.85')),
            bet('Total - Home', ('Over 1.5', '2.10'), ('Under 1.5', '1.70')),
            bet('Total - Away', ('Over 0.5', '1.45'), ('Under 0.5', '2.65')),
            bet('Clean Sheet - Home', ('Yes', '3.20'), ('No', '1.33')),
            bet('Clean Sheet - Away', ('Yes', '4.50'), ('No', '1.18')),
            bet('Asian Handicap', ('Home -1.5', '3.40'), ('Away +1.5', '1.30'),
                ('Home -0.5', '1.95'), ('Away +0.5', '1.85'), ('Home +0.5', '1.35'), ('Away -0.5', '3.10')),
            bet('Handicap Result', ('Home -1', '3.60'), ('Draw -1', '3.70'), ('Away -1', '1.85')),
            bet('First Half Winner', ('Home', '2.60'), ('Draw', '2.10'), ('Away', '4.40')),
            bet('Goals Over/Under First Half', ('Over 0.5', '1.40'), ('Under 0.5', '2.80'),
                ('Over 1.5', '2.90'), ('Under 1.5', '1.38')),
            bet('HT/FT Double', ('Home/Home', '3.10'), ('Draw/Home', '4.80'), ('Draw/Draw', '5.20'),
                ('Away/Away', '7.00'), ('Draw/Away', '9.00'), ('Home/Draw', '15.00')),
            bet('Highest Scoring half', ('1st Half', '3.25'), ('2nd Half', '2.05'), ('Draw', '3.40')),
            bet('Exact Score', ('1:0', '7.50'), ('2:0', '9.00'), ('2:1', '8.50'), ('3:1', '15.00'),
                ('0:0', '11.00'), ('1:1', '6.50'), ('2:2', '14.00'), ('0:1', '12.00'), ('1:2', '13.00')),
            bet('Results/Both Teams Score', ('Home/Yes', '3.60'), ('Home/No', '3.90'), ('Draw/Yes', '4.75'),
                ('Draw/No', '8.00'), ('Away/Yes', '6.50'), ('Away/No', '9.50')),
            bet('Result/Total Goals', ('Home/Over 2.5', '3.10'), ('Home/Under 2.5', '4.20'),
                ('Draw/Over 2.5', '9.00'), ('Draw/Under 2.5', '4.60'), ('Away/Over 2.5', '6.00'),
                ('Away/Under 2.5', '9.50')),
            bet('Team To Score First', ('Home', '1.72'), ('Draw', '11.00'), ('Away', '2.45')),
            bet('Win Both Halves', ('Home', '5.50'), ('Away', '11.00')),
            bet('Anytime Goal Scorer', ('Marcus Rashford', '2.60'), ('Bruno Fernandes', '3.20'),
                ('Rasmus Hojlund', '2.40'), ('Bukayo Saka', '2.90'), ('Gabriel Jesus', '2.75'),
                ('Martin Odegaard', '4.00'), ('No goal', '11.00')),
            bet('First Goal Scorer', ('Marcus Rashford', '6.50'), ('Rasmus Hojlund', '6.00'),
                ('Bukayo Saka', '7.50'), ('Gabriel Jesus', '7.00'), ('No goal', '11.00')),
            bet('Corners Over Under', ('Over 8.5', '1.55'), ('Under 8.5', '2.35'), ('Over 9.5', '1.85'),
                ('Under 9.5', '1.90'), ('Over 10.5', '2.30'), ('Under 10.5', '1.57')),
            bet('Corners 1x2', ('Home', '1.75'), ('Draw', '8.50'), ('Away', '2.30')),
            bet('Home Corners Over/Under', ('Over 4.5', '1.70'), ('Under 4.5', '2.05')),
            bet('Cards Over/Under', ('Over 3.5', '1.60'), ('Under 3.5', '2.20'), ('Over 4.5', '2.30'),
                ('Under 4.5', '1.57')),
            bet('RCARD', ('Yes', '4.50'), ('No', '1.18')),
        ]
        count = apply_feed_markets(event, parse_markets(bets))
        self.stdout.write(f'  [Markets] {count} on {event.name}')

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

    def _seed_banners(self):
        from apps.promotions.models import Banner
        base = 'https://images.unsplash.com'
        banners = [
            {
                'title': 'SLYK Aviator', 'subtitle': 'Cash out before the crash — win up to 100×',
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
