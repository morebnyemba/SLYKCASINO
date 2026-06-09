from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('player_id', models.IntegerField(db_index=True)),
                ('kind', models.CharField(
                    choices=[
                        ('bet_won', 'Bet won'),
                        ('bet_lost', 'Bet lost'),
                        ('deposit_confirmed', 'Deposit confirmed'),
                        ('withdrawal_processed', 'Withdrawal processed'),
                        ('bonus_credited', 'Bonus credited'),
                        ('promo_expiring', 'Promotion expiring soon'),
                        ('account_alert', 'Account alert'),
                    ],
                    max_length=30,
                )),
                ('title', models.CharField(max_length=120)),
                ('body', models.TextField(blank=True)),
                ('read', models.BooleanField(default=False)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'ordering': ['-created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['player_id', 'read'], name='notif_player_read_idx'),
        ),
    ]
