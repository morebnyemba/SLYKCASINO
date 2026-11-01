"""Three wallets, step 3 of 3: the database itself enforces the wallet rules.

- No bucket (or the total) can go negative, and the total always equals the
  sum of the three.
- Each kind of movement may only touch its own bucket: deposits only Deposit,
  bonuses only Bonus, withdrawals/fees/affiliate commission only Winnings.
- On Postgres a trigger makes the ledger append-only (no UPDATE; DELETE only
  for permanent account deletion, which opts in per transaction).
"""
from django.db import migrations, models
from django.db.models import F, Q

FIXED_BUCKET = {
    'deposit': 'deposit', 'deposit_refund': 'deposit', 'bonus': 'bonus',
    'withdrawal': 'winnings', 'withdrawal_hold': 'winnings', 'withdrawal_fee': 'winnings',
    'affiliate': 'winnings',
}


def _bucket_rule() -> Q:
    rule = Q(legacy=True)
    for kind, bucket in FIXED_BUCKET.items():
        rule |= Q(kind=kind, bucket=bucket)
    return rule | ~Q(kind__in=list(FIXED_BUCKET))


APPEND_ONLY = """
CREATE OR REPLACE FUNCTION wallet_ledger_append_only() RETURNS trigger AS $$
BEGIN
    -- Permanent account deletion (accounts.services) opts in explicitly.
    IF TG_OP = 'DELETE' AND current_setting('wallet.allow_ledger_delete', true) = 'on' THEN
        RETURN OLD;
    END IF;
    RAISE EXCEPTION 'wallet_ledger_entry is append-only: % refused', TG_OP;
END $$ LANGUAGE plpgsql;
DROP TRIGGER IF EXISTS wallet_ledger_append_only ON wallet_ledger_entry;
CREATE TRIGGER wallet_ledger_append_only BEFORE UPDATE OR DELETE ON wallet_ledger_entry
    FOR EACH ROW EXECUTE FUNCTION wallet_ledger_append_only();
"""
DROP_APPEND_ONLY = """
DROP TRIGGER IF EXISTS wallet_ledger_append_only ON wallet_ledger_entry;
DROP FUNCTION IF EXISTS wallet_ledger_append_only();
"""


def append_only(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute(APPEND_ONLY, params=None)


def drop_append_only(apps, schema_editor):
    if schema_editor.connection.vendor == 'postgresql':
        schema_editor.execute(DROP_APPEND_ONLY, params=None)


class Migration(migrations.Migration):

    dependencies = [
        ('wallet', '0012_split_balances'),
    ]

    operations = [
        migrations.AddIndex('ledgerentry', models.Index(fields=['wallet', 'bucket'], name='wallet_ledg_wallet__bucket_idx')),
        migrations.AddConstraint('wallet', models.CheckConstraint(check=Q(deposit_balance__gte=0), name='wallet_deposit_non_negative')),
        migrations.AddConstraint('wallet', models.CheckConstraint(check=Q(bonus_balance__gte=0), name='wallet_bonus_non_negative')),
        migrations.AddConstraint('wallet', models.CheckConstraint(check=Q(winnings_balance__gte=0), name='wallet_winnings_non_negative')),
        migrations.AddConstraint('wallet', models.CheckConstraint(
            check=Q(balance=F('deposit_balance') + F('bonus_balance') + F('winnings_balance')),
            name='wallet_balance_is_sum_of_buckets')),
        migrations.AddConstraint('ledgerentry', models.CheckConstraint(check=_bucket_rule(), name='ledger_kind_bucket_allowed')),
        migrations.AddConstraint('ledgerentry', models.CheckConstraint(
            check=Q(legacy=True) | ~Q(kind='deposit') | Q(amount__gt=0), name='ledger_deposit_is_credit')),
        migrations.AddConstraint('ledgerentry', models.CheckConstraint(
            check=Q(legacy=True) | ~Q(kind__in=['bet_stake', 'casino_debit', 'deposit_refund', 'withdrawal_fee'])
            | Q(amount__lte=0), name='ledger_stake_is_debit')),
        migrations.AddConstraint('ledgerentry', models.CheckConstraint(
            check=Q(legacy=True) | ~Q(kind__in=['bet_payout', 'casino_credit', 'bonus', 'affiliate'])
            | Q(amount__gte=0), name='ledger_payout_is_credit')),
        migrations.AddConstraint('ledgerentry', models.CheckConstraint(
            check=Q(legacy=True) | ~Q(kind='migration'), name='ledger_migration_only_legacy')),
        migrations.RunPython(append_only, drop_append_only),
    ]
