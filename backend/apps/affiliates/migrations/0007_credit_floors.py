from django.db import migrations, models
from django.db.models.functions import Coalesce


def backfill_active_since(apps, schema_editor):
    Affiliate = apps.get_model('affiliates', 'Affiliate')
    Affiliate.objects.filter(status='active', active_since__isnull=True).update(
        active_since=Coalesce('approved_at', 'created_at'))


class Migration(migrations.Migration):
    dependencies = [('affiliates', '0006_auto_payout')]

    operations = [
        migrations.AddField(model_name='affiliate', name='active_since',
                            field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='referral', name='credit_from',
                            field=models.DateTimeField(blank=True, null=True)),
        migrations.AddField(model_name='referral', name='linked_by',
                            field=models.CharField(blank=True, max_length=150)),
        migrations.RunPython(backfill_active_since, migrations.RunPython.noop),
    ]
