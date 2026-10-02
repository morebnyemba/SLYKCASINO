"""Take the seeded demo games out of the catalogue. They are deactivated rather
than deleted: rounds reference games (PROTECT) and play history must stay
intact. Inactive games are hidden from the lobby and can't be played. The
in-house Aviator crash game (slyk-aviator) is a real game and stays."""
from django.db import migrations

DEMO_SLUGS = (
    'lucky-slots', 'golden-wheel', 'mega-dice', 'blackjack-classic',
    'roulette-pro', 'live-baccarat', 'virtual-league',
)


def deactivate_demo_games(apps, schema_editor):
    Game = apps.get_model('casino', 'Game')
    Game.objects.filter(slug__in=DEMO_SLUGS).update(is_active=False)


class Migration(migrations.Migration):

    dependencies = [
        ('casino', '0003_game_category_crashround'),
    ]

    operations = [
        migrations.RunPython(deactivate_demo_games, migrations.RunPython.noop),
    ]
