"""Goal lines stop at 4.5 (services.MAX_GOAL_LINE): close the open over/under 5.5+ markets
already in the database. They are kept, not deleted, because bets may reference them."""
from decimal import Decimal

from django.db import migrations
from django.db.models import Q

KINDS = ('over_under', 'home_over_under', 'away_over_under', 'result_total', 'total_btts')
MAX = Decimal('4.5')


def close(apps, schema_editor):
    Market = apps.get_model('sportsbook', 'Market')
    Market.objects.filter(Q(kind__in=KINDS, metric='goals', settled=False, is_open=True)
                          & (Q(line__gt=MAX) | Q(line__lt=-MAX))).update(is_open=False)


class Migration(migrations.Migration):
    dependencies = [('sportsbook', '0037_leg_match_odds')]
    operations = [migrations.RunPython(close, migrations.RunPython.noop)]
