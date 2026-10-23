"""Dark mode moves to lighter blues (light-blue actions on a blue, not black,
background) with every token readable against the surfaces it sits on. A
stored dark theme still on the previous logo palette is switched over; one
the operator edited by hand is left as it is."""
from django.db import migrations

# The dark palette from 0006, frozen.
PREVIOUS_DARK = {'background': '#060D24',
 'foreground': '#EEF3FF',
 'card': '#0D1A3D',
 'card_foreground': '#EEF3FF',
 'primary': '#0149EB',
 'primary_foreground': '#FFFFFF',
 'secondary': '#1F6FFF',
 'secondary_foreground': '#FFFFFF',
 'muted': '#13234D',
 'muted_foreground': '#93A6D1',
 'accent': '#0CBBFB',
 'accent_foreground': '#031230',
 'gold': '#FDD01E',
 'gold_foreground': '#1A1200',
 'ring': '#1F6FFF',
 'border': 'rgba(255, 255, 255, 0.09)',
 'input': '#13234D',
 'destructive': '#FF6B6B',
 'live': '#FF5260',
 'live_foreground': '#FFFFFF',
 'tier_bronze': '#92400E',
 'tier_bronze_foreground': '#92400E',
 'tier_silver': '#6B7280',
 'tier_silver_foreground': '#6B7280',
 'win': '#36D399',
 'win_foreground': '#04122E',
 'down': '#FF6B6B',
 'chip': '#13234D',
 'chip_foreground': '#EEF3FF',
 'sidebar': '#081430',
 'sidebar_foreground': '#EEF3FF',
 'odds': '#15275A',
 'odds_hover': '#1C3473'}


def _norm(value):
    return str(value).replace(' ', '').lower()


def forwards(apps, schema_editor):
    from apps.branding.tokens import DEFAULT_DARK

    SiteTheme = apps.get_model('branding', 'SiteTheme')
    for theme in SiteTheme.objects.all():
        stored = theme.dark or {}
        if all(_norm(stored[k]) == _norm(PREVIOUS_DARK[k]) for k in stored if k in PREVIOUS_DARK):
            theme.dark = dict(DEFAULT_DARK)
            theme.save(update_fields=['dark'])


class Migration(migrations.Migration):

    dependencies = [
        ('branding', '0006_logo_palette'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
