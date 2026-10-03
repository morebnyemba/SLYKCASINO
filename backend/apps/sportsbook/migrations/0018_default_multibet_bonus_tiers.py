from decimal import Decimal

from django.db import migrations

# A starting ladder; operators edit it in the admin.
DEFAULT_TIERS = [(3, '3'), (4, '5'), (5, '8'), (6, '12'), (8, '20'), (10, '30'), (15, '50')]


def add_default_tiers(apps, schema_editor):
    Tier = apps.get_model('sportsbook', 'MultiBetBonusTier')
    if Tier.objects.exists():
        return
    Tier.objects.bulk_create([Tier(min_legs=n, percent=Decimal(p)) for n, p in DEFAULT_TIERS])


class Migration(migrations.Migration):

    dependencies = [
        ('sportsbook', '0017_booking_codes_multibet_bonus'),
    ]

    operations = [
        migrations.RunPython(add_default_tiers, migrations.RunPython.noop),
    ]
