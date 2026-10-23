"""Agents earn 30% of what their players lose, and can withdraw from $10.

New agents start on 30%. Existing agents still on the old 25% default move to
30%; anyone given a custom rate keeps it. The minimum withdrawal becomes $10
(it now applies to every method, the betting wallet included)."""
from decimal import Decimal

from django.db import migrations, models

OLD, NEW = Decimal('25'), Decimal('30')


def forwards(apps, schema_editor):
    Programme = apps.get_model('affiliates', 'AffiliateProgramme')
    Affiliate = apps.get_model('affiliates', 'Affiliate')
    for programme in Programme.objects.all():
        if programme.default_revshare_percent == OLD:
            programme.default_revshare_percent = NEW
        programme.min_payout = Decimal('10')
        programme.save(update_fields=['default_revshare_percent', 'min_payout'])
    Affiliate.objects.filter(revshare_percent=OLD).update(revshare_percent=NEW)


class Migration(migrations.Migration):

    dependencies = [
        ('affiliates', '0003_payouts'),
    ]

    operations = [
        migrations.AlterField(
            model_name='affiliateprogramme',
            name='default_revshare_percent',
            field=models.DecimalField(decimal_places=2, default=30, max_digits=5),
        ),
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
