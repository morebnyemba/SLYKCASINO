"""Three wallets, step 1 of 3: the new columns and the rules table
(the money moves in 0012, the database rules arrive in 0013)."""
from decimal import Decimal

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('wallet', '0010_withdrawal_turnover'),
    ]

    operations = [
        migrations.AddField('wallet', 'deposit_balance', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
        migrations.AddField('wallet', 'bonus_balance', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
        migrations.AddField('wallet', 'winnings_balance', models.DecimalField(decimal_places=2, default=0, max_digits=14)),
        migrations.AddField(
            'ledgerentry', 'bucket',
            models.CharField(choices=[('deposit', 'Deposit'), ('bonus', 'Bonus'), ('winnings', 'Winnings')],
                             default='winnings', max_length=10),
            preserve_default=False,
        ),
        migrations.AddField('ledgerentry', 'legacy', models.BooleanField(default=False)),
        migrations.AlterField(
            'ledgerentry', 'kind',
            models.CharField(choices=[
                ('deposit', 'Deposit'), ('deposit_refund', 'Deposit refund'), ('withdrawal', 'Withdrawal'),
                ('withdrawal_hold', 'Withdrawal held'), ('withdrawal_fee', 'Withdrawal fee'),
                ('bet_stake', 'Bet stake (debit)'), ('bet_payout', 'Bet payout (credit)'),
                ('casino_debit', 'Casino debit'), ('casino_credit', 'Casino credit'), ('bonus', 'Bonus credit'),
                ('adjustment', 'Manual adjustment'), ('affiliate', 'Affiliate commission'),
                ('migration', 'Wallet split'),
            ], max_length=20),
        ),
        migrations.AddField(
            'withdrawalsettings', 'fee_percent', models.DecimalField(decimal_places=2, default=Decimal('5.00'), max_digits=5)),
        migrations.AddField(
            'withdrawalrequest', 'fee', models.DecimalField(decimal_places=2, default=Decimal('0'), max_digits=12)),
        migrations.CreateModel(
            name='WalletRules',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('deposit_min_odds', models.DecimalField(decimal_places=2, default=Decimal('5.00'), max_digits=8)),
                ('bonus_min_odds', models.DecimalField(decimal_places=2, default=Decimal('10.00'), max_digits=8)),
                ('winnings_min_odds', models.DecimalField(decimal_places=2, default=Decimal('1.00'), max_digits=8)),
                ('updated_at', models.DateTimeField(auto_now=True)),
            ],
            options={'db_table': 'wallet_rules'},
        ),
    ]
