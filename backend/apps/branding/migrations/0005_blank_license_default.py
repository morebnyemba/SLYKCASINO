"""Licence text defaults to blank: the site claims a licence only once the
operator enters one. Existing rows are left exactly as the operator has them."""
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('branding', '0004_curacao_license'),
    ]

    operations = [
        migrations.AlterField(
            model_name='siteidentity',
            name='license_text',
            field=models.TextField(blank=True, default=''),
        ),
    ]
