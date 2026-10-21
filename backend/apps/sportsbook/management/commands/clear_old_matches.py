"""Close stale matches and delete old ones nobody bet on (what the hourly
task does): `manage.py clear_old_matches --dry-run` shows the counts only."""
from django.core.management.base import BaseCommand

from apps.sportsbook.services import clear_old_matches


class Command(BaseCommand):
    help = 'Close matches long past kick-off and delete old matches with no tickets.'

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Only count what would change.')

    def handle(self, *args, dry_run=False, **options):
        report = clear_old_matches(dry_run=dry_run)
        prefix = 'Would have ' if dry_run else ''
        self.stdout.write(
            f"{prefix}closed {report['closed']} stale matches, deleted {report['deleted']} old matches "
            f"with no tickets; kept {report['kept_with_tickets']} old matches that have tickets."
        )
