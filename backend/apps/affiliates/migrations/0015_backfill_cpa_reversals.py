"""Record the CPA audit already applied (reverse_cpa_overpayments --apply run
before CommissionReversal existed) so the operating pool gets that money back
on the next day it closes. Reads the clawback notes the command wrote:
'CPA clawback YYYY-MM-DD: <paid> -> <kept> (<reason>)'.

Assumes each clawed-back commission was final (approved/paid) before the audit
and became final when it was created (automatic approval). The command set a
rejected commission's decided_at to the moment of the audit, which is used as
the reversal time."""
import re
from datetime import datetime, time
from decimal import Decimal

from django.db import migrations
from django.utils import timezone

NOTE = re.compile(r'^CPA clawback (\d{4}-\d{2}-\d{2}): ([\d.]+) -> ([\d.]+) \((.*?)\)(?: by [^|]*)? \|')


def backfill(apps, schema_editor):
    Commission = apps.get_model('affiliates', 'Commission')
    CommissionReversal = apps.get_model('affiliates', 'CommissionReversal')
    RevenueDay = apps.get_model('revenue', 'RevenueDay')
    done = set(CommissionReversal.objects.values_list('commission_id', flat=True))
    rows = []
    for c in Commission.objects.filter(kind='cpa', note__startswith='CPA clawback').exclude(pk__in=done):
        m = NOTE.match(c.note or '')
        if not m:
            continue
        amount = Decimal(m.group(2)) - Decimal(m.group(3))
        if amount <= 0:
            continue
        if c.status == 'rejected' and c.decided_at:
            at = c.decided_at
        else:
            at = timezone.make_aware(datetime.combine(datetime.strptime(m.group(1), '%Y-%m-%d').date(), time(12)))
        counted = RevenueDay.objects.filter(day=timezone.localdate(c.created_at), closed_at__lt=at).exists()
        rows.append(CommissionReversal(commission_id=c.pk, affiliate_id=c.affiliate_id, amount=amount,
                                       reason=m.group(4)[:300], counted=counted, created_at=at))
    CommissionReversal.objects.bulk_create(rows)


class Migration(migrations.Migration):

    dependencies = [
        ('affiliates', '0014_commission_reversal'),
        ('revenue', '0009_affiliate_reversals'),
    ]

    operations = [migrations.RunPython(backfill, migrations.RunPython.noop)]
