"""Claw back deposit commissions (CPA) paid against the rules, since the
affiliate programme started. Dry run unless --apply.

    python manage.py reverse_cpa_overpayments                    # review everything
    python manage.py reverse_cpa_overpayments --affiliate AGENT  # one agent (code or id)
    python manage.py reverse_cpa_overpayments --apply --by ops   # reverse

See apps.affiliates.clawback for how the money is recovered.
"""
from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from apps.affiliates import clawback
from apps.affiliates.models import Affiliate


class Command(BaseCommand):
    help = 'Review (and with --apply, reverse) CPA commissions that exceed what the current rules pay.'

    def add_arguments(self, parser):
        parser.add_argument('--affiliate', action='append', default=[],
                            help='Agent code or id (repeatable). Default: every agent.')
        parser.add_argument('--apply', action='store_true', help='Reverse. Without it nothing changes.')
        parser.add_argument('--include-waived', action='store_true',
                            help='Also reverse commissions staff paid with the rules waived.')
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
        results = clawback.run(affiliate_ids=ids or None, apply=apply,
                               include_waived=opts['include_waived'], by=opts['by'])
        w = self.stdout.write
        w(('APPLYING' if apply else 'DRY RUN — nothing changed (add --apply)') + '\n')
        totals = {'excess': Decimal('0'), 'balance': Decimal('0'), 'wallet': Decimal('0'), 'carried': Decimal('0')}
        for res in results:
            a = Affiliate.objects.get(pk=res.affiliate_id)
            w(f'Agent {res.code} (#{res.affiliate_id}) — terms now: {a.cpa_amount} flat + {a.cpa_percent}% '
              f'(cap {a.cpa_cap}), minimum deposit {a.cpa_min_deposit}')
            for r in res.rows:
                tag = ' [staff waived rules — skipped]' if r.waived and not opts['include_waived'] else ''
                w(f'  commission #{r.commission_id} {r.status:<8} {r.created_at:%Y-%m-%d} player #{r.player_id}: '
                  f'first deposit {r.first_deposit}, deposits {r.deposits}, real stakes {r.real_turnover} — '
                  f'paid {r.paid}, rules pay {r.correct}, excess {r.excess} ({r.reason}){tag}')
            if apply:
                w(f'  -> reversed {res.reversed}: {res.from_balance} from affiliate balance, '
                  f'{res.from_wallet} from Winnings wallet, {res.carried} netted off future commissions')
                totals['balance'] += res.from_balance
                totals['wallet'] += res.from_wallet
                totals['carried'] += res.carried
            totals['excess'] += sum((r.excess for r in res.rows
                                     if r.status != 'pending' and (opts['include_waived'] or not r.waived)), Decimal('0'))
        w(f'\n{len(results)} agent(s); over-paid (approved/paid, excluding pending): {totals["excess"]}')
        if apply:
            w(f'recovered from balances {totals["balance"]}, from wallets {totals["wallet"]}, '
              f'carried against future commissions {totals["carried"]}')
