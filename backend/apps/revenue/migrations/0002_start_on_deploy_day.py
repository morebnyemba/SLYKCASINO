"""Pin the first day that counts to the day this is deployed (migrations run at
deploy), so the whole deploy day — from its midnight, including play before the
deploy — is shared. Without this the date would be set by the first page view
or hourly run, which after a late-night deploy could already be the next day."""
from django.db import migrations
from django.utils import timezone


def start_today(apps, schema_editor):
    RevenueSettings = apps.get_model('revenue', 'RevenueSettings')
    settings, created = RevenueSettings.objects.get_or_create(pk=1, defaults={'started_on': timezone.localdate()})
    if not created and settings.started_on is None:
        settings.started_on = timezone.localdate()
        settings.save(update_fields=['started_on'])


class Migration(migrations.Migration):

    dependencies = [
        ('revenue', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(start_today, migrations.RunPython.noop),
    ]
