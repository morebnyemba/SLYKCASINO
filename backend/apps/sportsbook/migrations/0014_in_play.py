from django.db import migrations, models

STATUSES = [
    ('pending', 'Pending (stake not confirmed)'),
    ('accepting', 'Accepting (in-play delay)'),
    ('open', 'Open'),
    ('won', 'Won'),
    ('lost', 'Lost'),
    ('void', 'Void'),
    ('rejected', 'Rejected (in-play)'),
]


class Migration(migrations.Migration):

    dependencies = [
        ('sportsbook', '0013_event_has_odds'),
    ]

    operations = [
        migrations.AddField(
            model_name='event',
            name='live_odds_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='last_goal_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name='event',
            name='live_main_open',
            field=models.BooleanField(default=False),
        ),
        migrations.AlterField(
            model_name='bet',
            name='status',
            field=models.CharField(choices=STATUSES, default='open', max_length=10),
        ),
        migrations.AlterField(
            model_name='betslip',
            name='status',
            field=models.CharField(choices=STATUSES, default='open', max_length=10),
        ),
    ]
