from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0002_player_responsible_gambling'),
    ]

    operations = [
        migrations.AddField(
            model_name='player',
            name='email_verified',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='player',
            name='email_verify_token',
            field=models.CharField(blank=True, default='', max_length=64),
        ),
    ]
