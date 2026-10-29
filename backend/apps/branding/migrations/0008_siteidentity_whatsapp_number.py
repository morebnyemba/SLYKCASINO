from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('branding', '0007_light_blue_dark_mode'),
    ]

    operations = [
        migrations.AddField(
            model_name='siteidentity',
            name='whatsapp_number',
            field=models.CharField(blank=True, default='', max_length=20),
        ),
    ]
