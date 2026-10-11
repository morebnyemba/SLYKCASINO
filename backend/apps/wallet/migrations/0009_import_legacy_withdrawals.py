"""Bring withdrawals made by the old instant flow (money taken off the balance,
no request recorded) into the payout queue, so staff can see and settle each one."""
from django.db import migrations

NOTE = 'Made before withdrawal requests existed — contact the player for where to send it.'


def forwards(apps, schema_editor):
    LedgerEntry = apps.get_model('wallet', 'LedgerEntry')
    WithdrawalRequest = apps.get_model('wallet', 'WithdrawalRequest')
    old = (LedgerEntry.objects.filter(kind='withdrawal', amount__lt=0)
           .exclude(reference__startswith='withdrawal:').select_related('wallet'))
    for entry in old:
        req = WithdrawalRequest.objects.create(
            player_id=entry.wallet.player_id, amount=-entry.amount, method='unknown', account_number='',
            status='requested', note=NOTE, legacy=True,
        )
        # Keep the original time. (The ledger is append-only, so the entry itself
        # is left as it is; a migration runs once, so nothing is imported twice.)
        WithdrawalRequest.objects.filter(pk=req.pk).update(created_at=entry.created_at)


class Migration(migrations.Migration):
    dependencies = [('wallet', '0008_legacy_withdrawals')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
