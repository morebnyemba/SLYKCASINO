"""The operator's rule: the minimum withdrawal is $1 (editable afterwards in
Admin → Withdrawals)."""
from decimal import Decimal

from django.db import migrations


def set_minimum(apps, schema_editor):
    WithdrawalSettings = apps.get_model('wallet', 'WithdrawalSettings')
    WithdrawalSettings.objects.update(min_amount=Decimal('1.00'))


class Migration(migrations.Migration):

    dependencies = [
        ('wallet', '0017_deposit_withdrawals'),
    ]

    operations = [
        migrations.RunPython(set_minimum, migrations.RunPython.noop),
    ]
