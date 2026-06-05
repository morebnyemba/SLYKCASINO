from decimal import Decimal

from apps.accounts import services as acc
from apps.wallet import services as w
from apps.wallet.models import LedgerEntry, Wallet
from apps.wallet.recovery import reconcile_wallet_ledger

print('--- provisioning (create_player also provisions wallet) ---')
p = acc.create_player(username='Alice', email='a@x.com', currency='USD')
print('player id:', p.id, 'wallet balance:', w.get_balance(p.id))

print('--- idempotent credit (same key twice) ---')
w.credit(player_id=p.id, amount=Decimal('100'), kind='deposit', idempotency_key='dep:1')
w.credit(player_id=p.id, amount=Decimal('100'), kind='deposit', idempotency_key='dep:1')
print('balance:', w.get_balance(p.id), '(expect 100.00)')
print('dep:1 entry count:', LedgerEntry.objects.filter(idempotency_key='dep:1').count(), '(expect 1)')

print('--- idempotent debit (same key twice) ---')
w.debit(player_id=p.id, amount=Decimal('30'), kind='bet_stake', idempotency_key='bet:1:stake')
w.debit(player_id=p.id, amount=Decimal('30'), kind='bet_stake', idempotency_key='bet:1:stake')
print('balance:', w.get_balance(p.id), '(expect 70.00)')
print('total entries:', LedgerEntry.objects.filter(wallet__player_id=p.id).count(), '(expect 2)')

print('--- recovery repairs cached-balance drift, idempotently ---')
Wallet.objects.filter(player_id=p.id).update(balance=Decimal('999.99'))
r1 = reconcile_wallet_ledger()
print('run1 repaired:', r1.repaired, 'balance:', w.get_balance(p.id), '(expect repaired=1, balance 70.00)')
r2 = reconcile_wallet_ledger()
print('run2 repaired:', r2.repaired, '(expect 0 — nothing to fix)')

print('--- cross-app: sportsbook.place_bet debits the wallet ---')
from apps.sportsbook import services as sb
bet = sb.place_bet(event='demo', stake=Decimal('20'), odds=Decimal('1.95'), player_id=p.id)
print('bet status:', bet.status, 'balance after stake:', w.get_balance(p.id), '(expect open, 50.00)')

print('--- celery autodiscovered recovery tasks ---')
from config.celery import app
print(sorted(t for t in app.tasks if t.startswith('apps.')))
print('SMOKE_OK')
