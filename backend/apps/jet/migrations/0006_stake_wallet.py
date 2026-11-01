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
        ("jet", "0005_bot_chat"),
    ]

    operations = [
        migrations.AddField("jetbet", "wallet", wallet_field(), preserve_default=False),
        migrations.AddConstraint("jetbet", models.CheckConstraint(check=models.Q(wallet__in=WALLETS), name="jet_bet_wallet_valid")),
    ]
