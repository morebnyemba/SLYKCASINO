"""Test-only helpers for the wallet."""
from contextlib import contextmanager

from django.db import connection


@contextmanager
def ledger_unlocked():
    """Let a test rewrite ledger rows (e.g. backdate them). On Postgres the
    ledger is append-only (migration 0013); this lifts that for the block, inside
    the test's own transaction. Never use it outside tests."""
    if connection.vendor != 'postgresql':
        yield
        return
    def toggle(action):
        with connection.cursor() as cursor:
            # ALTER TABLE refuses while deferred FK checks are pending: run them now.
            cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
            cursor.execute(f'ALTER TABLE wallet_ledger_entry {action} TRIGGER wallet_ledger_append_only')
            cursor.execute('SET CONSTRAINTS ALL DEFERRED')

    toggle('DISABLE')
    try:
        yield
    finally:
        toggle('ENABLE')
