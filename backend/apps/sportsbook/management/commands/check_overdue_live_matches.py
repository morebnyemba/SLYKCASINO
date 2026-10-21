"""Ask the odds feed about matches still marked live after they should be over
(what the every-2-minutes task does): `manage.py check_overdue_live_matches`."""
from django.core.management.base import BaseCommand

from apps.sportsbook.services import check_overdue_live_matches


class Command(BaseCommand):
    help = 'Get full time from the odds feed for matches still marked live 100+ minutes after kick-off.'

    def handle(self, *args, **options):
        r = check_overdue_live_matches()
        self.stdout.write(
            f"Asked the feed about {r['checked']} overdue live matches; it answered for {r['answered']}. "
            f"{r['still_live']} still live per the feed; {r['ended_no_result']} ended as NR (no result after 3h)."
        )
        if r['checked'] and not r['answered']:
            self.stdout.write('The feed answered for none: check the API key and the daily quota (celery_worker logs).')
