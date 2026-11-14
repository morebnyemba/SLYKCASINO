"""An Aviator stake can come from Deposit and Winnings together (Deposit first)."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("jet", "0006_stake_wallet"),
    ]

    operations = [
        migrations.AddField("jetbet", "stake_deposit", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
        migrations.AddField("jetbet", "stake_winnings", models.DecimalField(decimal_places=2, default=0, max_digits=10)),
    ]
