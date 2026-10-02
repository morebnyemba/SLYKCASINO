"""Delete the banners seed_demo used to create (BetBlits/SLYK Aviator, Welcome
Bonus, Weekly Tournaments). A row only matches if it has both a demo title and
the demo's stock photo, so an operator's own banner with the same title is
kept."""
from django.db import migrations

DEMO_BANNERS = {
    'BetBlits Aviator': 'photo-1606167668584-78701c57f13d',
    'SLYK Aviator': 'photo-1606167668584-78701c57f13d',
    'Welcome Bonus': 'photo-1596731498067-93a4b7174c93',
    'Weekly Tournaments': 'photo-1518895949257-7621c3c786d7',
}


def remove_demo_banners(apps, schema_editor):
    Banner = apps.get_model('promotions', 'Banner')
    for title, photo in DEMO_BANNERS.items():
        Banner.objects.filter(title=title, image_url__contains=photo).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('promotions', '0005_banner_sportsbook_placement'),
    ]

    operations = [
        migrations.RunPython(remove_demo_banners, migrations.RunPython.noop),
    ]
