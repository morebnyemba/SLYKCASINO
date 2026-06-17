from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0001_initial'),
    ]

    operations = [
        migrations.AddField(
            model_name='player',
            name='deposit_limit_daily',
            field=models.DecimalField(blank=True, decimal_places=2, max_digits=12, null=True),
        ),
        migrations.AddField(
            model_name='player',
            name='self_excluded',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='player',
            name='exclusion_ends_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
