"""Remove the demo matches seed_demo used to create (a football fixture plus a
basketball and a tennis match with made-up prices). The sportsbook now lists
only matches from the live feed. Provider-linked events are never touched."""
from django.db import migrations

DEMO_EVENTS = ('Man Utd vs Arsenal', 'Lakers vs Warriors', 'Federer vs Nadal')


def remove_demo_events(apps, schema_editor):
    Event = apps.get_model('sportsbook', 'Event')
    Event.objects.filter(name__in=DEMO_EVENTS, provider='', external_id__isnull=True).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('sportsbook', '0015_event_league'),
    ]

    operations = [
        migrations.RunPython(remove_demo_events, migrations.RunPython.noop),
    ]
