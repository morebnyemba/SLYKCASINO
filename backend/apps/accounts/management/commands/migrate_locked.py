"""`migrate`, one at a time: holds a Postgres advisory lock while migrating, so
the container's entrypoint and a hand-run `manage.py migrate_locked` (or two
replicas booting together) can't both create the same table and crash. The
second run waits, then finds nothing left to apply. Elsewhere it is `migrate`."""
from django.core.management.commands.migrate import Command as MigrateCommand
from django.db import connection

LOCK_ID = 7_314_002_118  # any fixed bigint, shared by every caller


class Command(MigrateCommand):
    help = 'Apply migrations under a Postgres advisory lock (safe to run concurrently).'

    def handle(self, *args, **options):
        if connection.vendor != 'postgresql':
            return super().handle(*args, **options)
        with connection.cursor() as cursor:
            self.stdout.write('[migrate] waiting for the migration lock…')
            cursor.execute('SELECT pg_advisory_lock(%s)', [LOCK_ID])
            try:
                return super().handle(*args, **options)
            finally:
                cursor.execute('SELECT pg_advisory_unlock(%s)', [LOCK_ID])
