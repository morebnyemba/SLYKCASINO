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
        ("sportsbook", "0022_ticket_codes"),
    ]

    operations = [
        migrations.AddField("bet", "wallet", wallet_field(), preserve_default=False),
        migrations.AddField("betslip", "wallet", wallet_field(), preserve_default=False),
        migrations.AddConstraint("bet", models.CheckConstraint(check=models.Q(wallet__in=WALLETS), name="sportsbook_bet_wallet_valid")),
        migrations.AddConstraint("betslip", models.CheckConstraint(check=models.Q(wallet__in=WALLETS), name="sportsbook_betslip_wallet_valid")),
    ]
