"""Show or clear the revenue-share password lock (recovery if the password is lost).

    python manage.py revenue_lock            # is it locked, and by whom
    python manage.py revenue_lock --clear    # remove the lock for everyone
"""
from django.core.management.base import BaseCommand

from apps.revenue import lock


class Command(BaseCommand):
    help = 'Show or clear the revenue-share password lock.'

    def add_arguments(self, parser):
        parser.add_argument('--clear', action='store_true', help='Remove the lock (everyone with access sees it again).')

    def handle(self, *args, **opts):
        cfg = lock._cfg()
        if opts['clear']:
            if not lock.is_locked(cfg):
                self.stdout.write('The revenue share is not locked.')
                return
            lock.clear(by='server command')
            self.stdout.write(self.style.SUCCESS('Lock removed.'))
            return
        if lock.is_locked(cfg):
            self.stdout.write(f'Locked by {cfg.lock_owner.get_username() if cfg.lock_owner_id else "?"} since {cfg.lock_set_at:%Y-%m-%d %H:%M}.')
        else:
            self.stdout.write('Not locked.')
