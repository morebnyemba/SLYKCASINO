"""New BetBlits logo (indigo-navy wordmark, cyan→violet ring, yellow bolt):
the theme moves to its palette. A stored theme still on the previous defaults
is switched over; a side the operator edited by hand is left as it is."""
from django.db import migrations

# The defaults this replaces (0007's light and dark), frozen.
PREVIOUS_LIGHT = {'background': '#F2F6FF',
 'foreground': '#0A1433',
 'card': '#FFFFFF',
 'card_foreground': '#0A1433',
 'primary': '#0149EB',
 'primary_foreground': '#FFFFFF',
 'secondary': '#0B5CF0',
 'secondary_foreground': '#FFFFFF',
 'muted': '#E2EAFC',
 'muted_foreground': '#4D5F8C',
 'accent': '#0A8FD0',
 'accent_foreground': '#FFFFFF',
 'gold': '#B07A00',
 'gold_foreground': '#FFFFFF',
 'ring': '#0149EB',
 'border': '#C7D4F2',
 'input': '#EAF0FE',
 'destructive': '#DC2626',
 'live': '#DC2626',
 'live_foreground': '#FFFFFF',
 'tier_bronze': '#92400E',
 'tier_bronze_foreground': '#92400E',
 'tier_silver': '#6B7280',
 'tier_silver_foreground': '#6B7280',
 'win': '#15924E',
 'win_foreground': '#FFFFFF',
 'down': '#DC2626',
 'chip': '#EAF0FE',
 'chip_foreground': '#0A1433',
 'sidebar': '#FFFFFF',
 'sidebar_foreground': '#0A1433',
 'odds': '#E8EFFE',
 'odds_hover': '#D8E4FD'}

PREVIOUS_DARK = {'background': '#0E2250',
 'foreground': '#F2F6FF',
 'card': '#15306A',
 'card_foreground': '#F2F6FF',
 'primary': '#1F66F0',
 'primary_foreground': '#FFFFFF',
 'secondary': '#5AAEFF',
 'secondary_foreground': '#04122E',
 'muted': '#1B3877',
 'muted_foreground': '#B9CBF0',
 'accent': '#46D3FF',
 'accent_foreground': '#04122E',
 'gold': '#FDD01E',
 'gold_foreground': '#1A1200',
 'ring': '#5AAEFF',
 'border': 'rgba(190, 210, 255, 0.16)',
 'input': '#1A3673',
 'destructive': '#FF8080',
 'live': '#DC2F3E',
 'live_foreground': '#FFFFFF',
 'tier_bronze': '#E39B54',
 'tier_bronze_foreground': '#E39B54',
 'tier_silver': '#C7CFDD',
 'tier_silver_foreground': '#C7CFDD',
 'win': '#3EE0A0',
 'win_foreground': '#04122E',
 'down': '#FF8080',
 'chip': '#1B3877',
 'chip_foreground': '#F2F6FF',
 'sidebar': '#0B1C44',
 'sidebar_foreground': '#F2F6FF',
 'odds': '#1D3D84',
 'odds_hover': '#26499C'}


def _norm(value):
    return str(value).replace(' ', '').lower()


def _on_previous(stored, previous):
    return all(_norm(stored[k]) == _norm(previous[k]) for k in stored if k in previous)


def forwards(apps, schema_editor):
    from apps.branding.tokens import DEFAULT_DARK, DEFAULT_LIGHT

    SiteTheme = apps.get_model('branding', 'SiteTheme')
    for theme in SiteTheme.objects.all():
        fields = []
        if _on_previous(theme.light or {}, PREVIOUS_LIGHT):
            theme.light = dict(DEFAULT_LIGHT)
            fields.append('light')
        if _on_previous(theme.dark or {}, PREVIOUS_DARK):
            theme.dark = dict(DEFAULT_DARK)
            fields.append('dark')
        if fields:
            theme.save(update_fields=fields)


class Migration(migrations.Migration):

    dependencies = [
        ('branding', '0008_siteidentity_whatsapp_number'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
