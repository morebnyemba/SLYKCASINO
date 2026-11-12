from django.db import migrations, models
from django.utils import timezone


def start_now(apps, schema_editor):
    # Agents start earning on Aviator from the deploy, never for earlier rounds.
    apps.get_model('affiliates', 'AffiliateProgramme').objects.update(aviator_commission_since=timezone.now())


class Migration(migrations.Migration):
    dependencies = [('affiliates', '0007_credit_floors')]

    operations = [
        migrations.AddField(model_name='affiliateprogramme', name='aviator_commission',
                            field=models.BooleanField(default=True)),
        migrations.AddField(model_name='affiliateprogramme', name='aviator_commission_percent',
                            field=models.DecimalField(blank=True, decimal_places=2, max_digits=5, null=True)),
        migrations.AddField(model_name='affiliateprogramme', name='aviator_commission_since',
                            field=models.DateTimeField(blank=True, null=True)),
        migrations.RunPython(start_now, migrations.RunPython.noop),
    ]
