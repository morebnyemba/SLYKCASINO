"""Put withdrawals made by the old instant flow into the payout queue.

    python manage.py import_old_withdrawals          # import and report
    python manage.py import_old_withdrawals --dry-run

Safe to run any number of times: an old withdrawal that already has its queue
entry (same player, amount and time) is skipped.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.wallet.models import LedgerEntry, WithdrawalRequest

NOTE = 'Made before withdrawal requests existed — contact the player for where to send it.'


class Command(BaseCommand):
    help = 'Import withdrawals made before requests existed into the Withdrawals queue.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only list what would be imported.')

    def handle(self, *args, **opts):
        old = (LedgerEntry.objects.filter(kind='withdrawal', amount__lt=0)
               .exclude(reference__startswith='withdrawal:').select_related('wallet').order_by('created_at'))
        found = imported = 0
        with transaction.atomic():
            for entry in old:
                found += 1
                player_id, amount = entry.wallet.player_id, -entry.amount
                if WithdrawalRequest.objects.filter(legacy=True, player_id=player_id, amount=amount,
                                                    created_at=entry.created_at).exists():
                    continue
                self.stdout.write(f'  player #{player_id}: ${amount} on {entry.created_at:%Y-%m-%d %H:%M}')
                if not opts['dry_run']:
                    req = WithdrawalRequest.objects.create(
                        player_id=player_id, amount=amount, method='unknown', account_number='',
                        status='requested', note=NOTE, legacy=True,
                    )
                    WithdrawalRequest.objects.filter(pk=req.pk).update(created_at=entry.created_at)
                imported += 1
        verb = 'would import' if opts['dry_run'] else 'imported'
        self.stdout.write(self.style.SUCCESS(
            f'{found} old withdrawal(s) found, {verb} {imported}, {found - imported} already in the queue.'))
