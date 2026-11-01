"""Stakes remember the wallet they were paid from, and the database refuses
any other value. Bets placed before the three-wallet split came from the old
single balance, which became Winnings."""
from django.db import migrations, models

WALLETS = ["deposit", "bonus", "winnings"]


def wallet_field():
    return models.CharField(
        choices=[("deposit", "Deposit"), ("bonus", "Bonus"), ("winnings", "Winnings")], default="winnings", max_length=10,
    )


class Migration(migrations.Migration):

    dependencies = [
        ("casino", "0004_deactivate_demo_games"),
    ]

    operations = [
        migrations.AddField("gameround", "wallet", wallet_field(), preserve_default=False),
        migrations.AddField("crashround", "wallet", wallet_field(), preserve_default=False),
        migrations.AddConstraint("gameround", models.CheckConstraint(check=models.Q(wallet__in=WALLETS), name="casino_round_wallet_valid")),
        migrations.AddConstraint("crashround", models.CheckConstraint(check=models.Q(wallet__in=WALLETS), name="casino_crash_wallet_valid")),
    ]
