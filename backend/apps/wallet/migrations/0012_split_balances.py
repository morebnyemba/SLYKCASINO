"""Split every wallet into three balances: Deposit, Bonus and Winnings.

Existing money moves like this (the operator's decision): bonus money still
locked by unmet wagering goes to Bonus; everything else goes to Winnings, so
nobody loses money they could withdraw the day before. Deposit starts at 0.

Pre-split ledger rows are kept as they were and marked `legacy` (all on the
Winnings bucket); the move of locked bonus is recorded as a pair of legacy
`migration` entries, so every bucket still equals the sum of its entries.
"""
from decimal import Decimal

from django.db import migrations
from django.db.models import Sum


def split(apps, schema_editor):
    Wallet = apps.get_model('wallet', 'Wallet')
    LedgerEntry = apps.get_model('wallet', 'LedgerEntry')
    Claim = apps.get_model('promotions', 'PromotionClaim')
    LedgerEntry.objects.update(legacy=True, bucket='winnings')
    for wallet in Wallet.objects.all().iterator():
        total = LedgerEntry.objects.filter(wallet=wallet).aggregate(t=Sum('amount'))['t'] or Decimal('0')
        locked = Decimal('0')
        for claim in Claim.objects.filter(player_id=wallet.player_id, status='active', bonus_credited=True):
            if claim.wagering_required - claim.wagering_progress > 0:
                locked += claim.bonus_amount
        bonus = max(min(locked, total), Decimal('0'))
        if bonus > 0:
            for bucket, amount in (('winnings', -bonus), ('bonus', bonus)):
                LedgerEntry.objects.create(
                    wallet=wallet, idempotency_key=f'wallet-split:{wallet.pk}:{bucket}', amount=amount,
                    kind='migration', bucket=bucket, legacy=True, reference='wallet-split',
                )
        wallet.balance = total
        wallet.deposit_balance = Decimal('0')
        wallet.bonus_balance = bonus
        wallet.winnings_balance = total - bonus
        wallet.save(update_fields=['balance', 'deposit_balance', 'bonus_balance', 'winnings_balance'])


class Migration(migrations.Migration):

    dependencies = [
        ('wallet', '0011_three_wallets'),
        ('promotions', '0010_deposit_bonus_tiers'),
    ]

    operations = [
        migrations.RunPython(split, migrations.RunPython.noop),
    ]
