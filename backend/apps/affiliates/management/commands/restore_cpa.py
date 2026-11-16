"""Give back deposit commissions the CPA audit reversed although they met the
rules in force when they were paid (1x the first deposit in real money,
customer not linked to the agent; on flat-CPA terms only the % part). Dry run unless --apply.

    python manage.py restore_cpa                 # review
    python manage.py restore_cpa --apply --by ops

See apps.affiliates.restore.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from apps.affiliates import restore
from apps.affiliates.models import Affiliate


class Command(BaseCommand):
    help = 'Review (and with --apply, restore) audited CPA commissions that met the rules in force when paid.'

    def add_arguments(self, parser):
        parser.add_argument('--affiliate', action='append', default=[], help='Agent code or id (repeatable).')
        parser.add_argument('--apply', action='store_true', help='Restore. Without it nothing changes.')
        parser.add_argument('--by', default='', help='Who ran it (written to the notes).')

    def handle(self, *args, **opts):
        ids = []
        for ref in opts['affiliate']:
            a = Affiliate.objects.filter(pk=int(ref)).first() if ref.isdigit() else None
            a = a or Affiliate.objects.filter(code__iexact=ref).first()
            if a is None:
                raise CommandError(f'no agent {ref!r}')
            ids.append(a.pk)
        apply = opts['apply']
        results = restore.run(affiliate_ids=ids or None, apply=apply, by=opts['by'])
        w = self.stdout.write
        w(('APPLYING' if apply else 'DRY RUN — nothing changed (add --apply)') + '\n')
        total, count, wallet, kept = Decimal('0'), 0, Decimal('0'), Decimal('0')
        for res in results:
            due = [r for r in res.rows if r.restore]
            stay = [r for r in res.rows if not r.restore]
            w(f'Agent {res.code} (#{res.affiliate_id}): restore {len(due)} = {res.due}, '
              f'stays reversed {len(stay)} = {sum((r.amount for r in stay), Decimal("0"))}')
            for r in res.rows:
                w(f'  {"RESTORE" if r.restore else "keep   "} commission #{r.commission_id} '
                  f'{"player #" + str(r.player_id) if r.player_id else "deleted customer"}: '
                  f'{r.kept} -> {r.target if r.restore else r.kept} of {r.paid} ({r.why})')
            if apply:
                w(f'  -> restored {res.restored}, of which {res.to_wallet} paid back to the Winnings wallet')
            total += res.due
            count += len(due)
            wallet += res.to_wallet
            kept += sum((r.amount for r in stay), Decimal('0'))
        w(f'\nTo restore: {count} commission(s), {total}. Stays reversed: {kept}.')
        if apply:
            w(f'Paid back to Winnings wallets: {wallet}; the rest went back to agent balances.')
