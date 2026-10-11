"""Switch on the withdrawal notice: players whose withdrawal was made before
6:00 PM on 11 October 2026, or was rejected, are asked to request it again
or contact support. Staff can edit or switch it off under Admin → Banners."""
from django.db import migrations

TITLE = 'Withdrawal update'
MESSAGE = (
    'If you requested a withdrawal before 6:00 PM on 11 October, or your withdrawal was rejected, '
    'please submit a new withdrawal request from your wallet — or tap Contact support to chat with our team '
    'and we’ll sort it out for you.'
)


def forwards(apps, schema_editor):
    SiteAnnouncement = apps.get_model('promotions', 'SiteAnnouncement')
    SiteAnnouncement.objects.update_or_create(pk=1, defaults={
        'enabled': True, 'title': TITLE, 'message': MESSAGE, 'tone': 'warning',
        'show_withdraw_button': True, 'show_support_button': True, 'updated_by': 'system',
    })


class Migration(migrations.Migration):
    dependencies = [('promotions', '0008_site_announcement')]
    operations = [migrations.RunPython(forwards, migrations.RunPython.noop)]
