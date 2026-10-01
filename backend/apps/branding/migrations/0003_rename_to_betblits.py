"""Rebrand SLÝKBETS -> BetBlits: new defaults, and move the live identity row
over too unless the operator already set their own name in the admin."""
from django.db import migrations, models

OLD_NAMES = ('SLÝKBETS', 'SLYKBETS')
OLD_LICENSE = ('Licensed and regulated by the Lotteries and Gaming Board of Zimbabwe. '
               'Licence No. LGB/SLYKBETS/2026 (demo).')
NEW_LICENSE = ('Licensed and regulated by the Lotteries and Gaming Board of Zimbabwe. '
               'Licence No. LGB/BETBLITS/2026 (demo).')


def rebrand(apps, schema_editor):
    SiteIdentity = apps.get_model('branding', 'SiteIdentity')
    SiteIdentity.objects.filter(site_name__in=OLD_NAMES).update(site_name='BetBlits')
    SiteIdentity.objects.filter(license_text=OLD_LICENSE).update(license_text=NEW_LICENSE)


class Migration(migrations.Migration):

    dependencies = [
        ('branding', '0002_siteidentity'),
    ]

    operations = [
        migrations.AlterField(
            model_name='siteidentity',
            name='site_name',
            field=models.CharField(default='BetBlits', max_length=80),
        ),
        migrations.AlterField(
            model_name='siteidentity',
            name='license_text',
            field=models.TextField(blank=True, default=NEW_LICENSE),
        ),
        migrations.RunPython(rebrand, migrations.RunPython.noop),
    ]
