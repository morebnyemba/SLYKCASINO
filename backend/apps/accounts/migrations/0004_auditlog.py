from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0003_player_email_verification'),
    ]

    operations = [
        migrations.CreateModel(
            name='AuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('player_id', models.BigIntegerField(blank=True, db_index=True, null=True)),
                ('event_type', models.CharField(
                    choices=[
                        ('login', 'Login'),
                        ('logout', 'Logout'),
                        ('register', 'Register'),
                        ('deposit', 'Deposit'),
                        ('withdrawal', 'Withdrawal'),
                        ('bet_placed', 'Bet placed'),
                        ('bet_settled', 'Bet settled'),
                        ('casino_spin', 'Casino spin'),
                        ('promo_claim', 'Promotion claimed'),
                        ('self_exclude', 'Self-exclusion'),
                        ('limit_set', 'Deposit limit set'),
                        ('email_verified', 'Email verified'),
                        ('password_reset', 'Password reset'),
                        ('data_export', 'Data export'),
                        ('account_deleted', 'Account deleted'),
                    ],
                    db_index=True,
                    max_length=30,
                )),
                ('ip_address', models.GenericIPAddressField(blank=True, null=True)),
                ('metadata', models.JSONField(blank=True, default=dict)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'db_table': 'accounts_audit_log',
                'ordering': ['-created_at'],
            },
        ),
    ]
