"""The coming-soon catalogue (apps.casino.catalog): 500+ titles shown with "Notify me" until
each is connected. Existing games with the same slug are left alone."""
from django.db import migrations


def seed(apps, schema_editor):
    from apps.casino.catalog import entries
    Game = apps.get_model('casino', 'Game')
    have = set(Game.objects.values_list('slug', flat=True))
    Game.objects.bulk_create([Game(**e, rtp=0, is_active=True, coming_soon=True) for e in entries() if e['slug'] not in have])


def unseed(apps, schema_editor):
    Game = apps.get_model('casino', 'Game')
    Game.objects.filter(coming_soon=True, rounds__isnull=True).delete()


class Migration(migrations.Migration):
    dependencies = [('casino', '0006_coming_soon_games')]
    operations = [migrations.RunPython(seed, unseed)]
