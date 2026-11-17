"""Put every agent's deposit commission (CPA) on one % of the first deposit, and
bring commissions already paid at a higher rate down to it. Dry run unless --apply.

    python manage.py reprice_cpa                       # review at 10%
    python manage.py reprice_cpa --apply --by ops      # set every agent to 10% and take back the excess
    python manage.py reprice_cpa --percent 10 --affiliate AGENT

Eligibility isn't re-judged (commissions restore_cpa gave back stay earned);
only amounts above the rate are cut. See apps.affiliates.reprice.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from apps.affiliates import reprice
from apps.affiliates.models import Affiliate


class Command(BaseCommand):
    help = 'Set every agent to one CPA % and cut commissions paid above it (dry run unless --apply).'

    def add_arguments(self, parser):
        parser.add_argument('--percent', default=str(reprice.DEFAULT_PERCENT), help='CPA % of the first deposit (default 10).')
        parser.add_argument('--affiliate', action='append', default=[], help='Agent code or id (repeatable). Default: all.')
        parser.add_argument('--apply', action='store_true', help='Change terms and take back the excess.')
        parser.add_argument('--by', default='', help='Who ran it (written to the notes).')

    def handle(self, *args, **opts):
        percent = Decimal(opts['percent'])
        if not Decimal('0') <= percent <= Decimal('100'):
            raise CommandError('--percent must be between 0 and 100')
        ids = []
        for ref in opts['affiliate']:
            a = Affiliate.objects.filter(pk=int(ref)).first() if ref.isdigit() else None
            a = a or Affiliate.objects.filter(code__iexact=ref).first()
            if a is None:
                raise CommandError(f'no agent {ref!r}')
            ids.append(a.pk)
        apply = opts['apply']
        w = self.stdout.write
        w(('APPLYING' if apply else 'DRY RUN — nothing changed (add --apply)') + f' — deposit commission {percent}%\n')
        if apply and not ids:
            w(f'Terms: {reprice.set_terms(percent)} agent(s) moved to {percent}%; new agents start on {percent}%.')
        results = reprice.run(percent=percent, affiliate_ids=ids or None, apply=apply, by=opts['by'])
        total = Decimal('0')
        for res in results:
            w(f'Agent {res.code} (#{res.affiliate_id})')
            for r in res.rows:
                who = f'player #{r.player_id}' if r.player_id else 'deleted customer'
                w(f'  commission #{r.commission_id} {r.status:<8} {r.created_at:%Y-%m-%d} {who}: '
                  f'first deposit {r.first_deposit} — paid {r.paid} -> {r.correct} (excess {r.excess})')
            if apply:
                w(f'  -> taken back {res.reversed}: {res.from_balance} from affiliate balance, '
                  f'{res.from_wallet} from Winnings wallet, {res.carried} netted off future commissions')
            total += sum((r.excess for r in res.rows if r.status != 'pending'), Decimal('0'))
        w(f'\n{len(results)} agent(s); paid above {percent}% (approved/paid, excluding pending): {total}')
