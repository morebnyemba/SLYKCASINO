"""Licensing moves to Curaçao: new default licence text, and the live identity
row follows unless the operator already wrote their own in the admin."""
from django.db import migrations, models

OLD_LICENSES = (
    'Licensed and regulated by the Lotteries and Gaming Board of Zimbabwe. '
    'Licence No. LGB/BETBLITS/2026 (demo).',
    'Licensed and regulated by the Lotteries and Gaming Board of Zimbabwe. '
    'Licence No. LGB/SLYKBETS/2026 (demo).',
)
NEW_LICENSE = 'Operated under a gaming licence issued by the Curaçao Gaming Authority (CGA).'


def move_to_curacao(apps, schema_editor):
    SiteIdentity = apps.get_model('branding', 'SiteIdentity')
    SiteIdentity.objects.filter(license_text__in=OLD_LICENSES).update(license_text=NEW_LICENSE)


class Migration(migrations.Migration):

    dependencies = [
        ('branding', '0003_rename_to_betblits'),
    ]

    operations = [
        migrations.AlterField(
            model_name='siteidentity',
            name='license_text',
            field=models.TextField(blank=True, default=NEW_LICENSE),
        ),
        migrations.RunPython(move_to_curacao, migrations.RunPython.noop),
    ]
