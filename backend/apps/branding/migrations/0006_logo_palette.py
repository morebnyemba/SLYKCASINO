"""Switch the stored site theme to the BetBlits logo palette (blue & gold) —
but only where the operator never customised it: a mode is replaced when it
still matches the old indigo default or the green logo preset on every token it
holds. Any hand-edited mode is left exactly as it is (the new palette is one
click away as a preset in Admin → Branding)."""
from django.db import migrations

OLD_LIGHT = {'background': '#F3F4FC',
 'foreground': '#1A1538',
 'card': '#FFFFFF',
 'card_foreground': '#1A1538',
 'primary': '#312783',
 'primary_foreground': '#FFFFFF',
 'secondary': '#4338CA',
 'secondary_foreground': '#FFFFFF',
 'muted': '#E6E5F7',
 'muted_foreground': '#5C5A86',
 'accent': '#5B53D6',
 'accent_foreground': '#FFFFFF',
 'gold': '#B8860B',
 'gold_foreground': '#FFFFFF',
 'ring': '#312783',
 'border': '#C9CBEC',
 'input': '#ECEDF8',
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
 'chip': '#ECEDF8',
 'chip_foreground': '#1A1538',
 'sidebar': '#FFFFFF',
 'sidebar_foreground': '#1A1538',
 'odds': '#EEEFFA',
 'odds_hover': '#E0E1F6'}

OLD_DARK = {'background': '#0C0820',
 'foreground': '#F2F1FB',
 'card': '#191347',
 'card_foreground': '#F2F1FB',
 'primary': '#312783',
 'primary_foreground': '#FFFFFF',
 'secondary': '#6C63E8',
 'secondary_foreground': '#FFFFFF',
 'muted': '#1E1850',
 'muted_foreground': '#9D99C8',
 'accent': '#8079EE',
 'accent_foreground': '#FFFFFF',
 'gold': '#E6B84C',
 'gold_foreground': '#1A1538',
 'ring': '#6C63E8',
 'border': 'rgba(255, 255, 255, 0.09)',
 'input': '#1E1850',
 'destructive': '#FF6B6B',
 'live': '#FF5260',
 'live_foreground': '#FFFFFF',
 'tier_bronze': '#92400E',
 'tier_bronze_foreground': '#92400E',
 'tier_silver': '#6B7280',
 'tier_silver_foreground': '#6B7280',
 'win': '#36D399',
 'win_foreground': '#0C0820',
 'down': '#FF6B6B',
 'chip': '#1E1850',
 'chip_foreground': '#F2F1FB',
 'sidebar': '#110B2E',
 'sidebar_foreground': '#F2F1FB',
 'odds': '#241D5C',
 'odds_hover': '#2F2772'}

GREEN_LIGHT = {'background': '#F3F8F4',
 'foreground': '#0B1F10',
 'card': '#FFFFFF',
 'card_foreground': '#0B1F10',
 'primary': '#0E3B17',
 'primary_foreground': '#FFFFFF',
 'secondary': '#15803D',
 'secondary_foreground': '#FFFFFF',
 'muted': '#E3F0E6',
 'muted_foreground': '#4F6B56',
 'accent': '#16A34A',
 'accent_foreground': '#FFFFFF',
 'gold': '#B8860B',
 'gold_foreground': '#FFFFFF',
 'ring': '#15803D',
 'border': '#C8DDCD',
 'input': '#EAF3EC',
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
 'chip': '#EAF3EC',
 'chip_foreground': '#0B1F10',
 'sidebar': '#FFFFFF',
 'sidebar_foreground': '#0B1F10',
 'odds': '#E6F2E9',
 'odds_hover': '#D5EADB'}

GREEN_DARK = {'background': '#060F08',
 'foreground': '#EEF8EF',
 'card': '#0E1C11',
 'card_foreground': '#EEF8EF',
 'primary': '#0E3B17',
 'primary_foreground': '#FFFFFF',
 'secondary': '#16A34A',
 'secondary_foreground': '#FFFFFF',
 'muted': '#13281A',
 'muted_foreground': '#93B39A',
 'accent': '#22C55E',
 'accent_foreground': '#04150A',
 'gold': '#F5B400',
 'gold_foreground': '#1A1200',
 'ring': '#22C55E',
 'border': 'rgba(255, 255, 255, 0.09)',
 'input': '#13281A',
 'destructive': '#FF6B6B',
 'live': '#FF5260',
 'live_foreground': '#FFFFFF',
 'tier_bronze': '#92400E',
 'tier_bronze_foreground': '#92400E',
 'tier_silver': '#6B7280',
 'tier_silver_foreground': '#6B7280',
 'win': '#4ADE80',
 'win_foreground': '#04150A',
 'down': '#FF6B6B',
 'chip': '#13281A',
 'chip_foreground': '#EEF8EF',
 'sidebar': '#081509',
 'sidebar_foreground': '#EEF8EF',
 'odds': '#143A1C',
 'odds_hover': '#1B4A25'}


def _norm(value):
    return str(value).replace(' ', '').lower()


def _untouched(stored, presets):
    if not stored:
        return True
    return any(all(_norm(stored[k]) == _norm(p[k]) for k in stored if k in p) for p in presets)


def forwards(apps, schema_editor):
    from apps.branding.tokens import DEFAULT_DARK, DEFAULT_LIGHT

    SiteTheme = apps.get_model('branding', 'SiteTheme')
    for theme in SiteTheme.objects.all():
        changed = []
        if _untouched(theme.light, (OLD_LIGHT, GREEN_LIGHT)):
            theme.light = dict(DEFAULT_LIGHT)
            changed.append('light')
        if _untouched(theme.dark, (OLD_DARK, GREEN_DARK)):
            theme.dark = dict(DEFAULT_DARK)
            changed.append('dark')
        if changed:
            theme.save(update_fields=changed)


class Migration(migrations.Migration):

    dependencies = [
        ('branding', '0005_blank_license_default'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
