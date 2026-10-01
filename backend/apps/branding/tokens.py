"""The editable color-token schema for the site theme.

Keys mirror the CSS custom properties defined in
`packages/ui/src/styles/globals.css` (minus the `tier-gold*` aliases, which
are computed from `gold`, and `--radius`, which isn't a color). Defaults below
are copied verbatim from that file's `:root` / `[data-theme='dark']` blocks so
seeding this model changes nothing visually until an operator edits it.
"""
from __future__ import annotations

TOKEN_KEYS: tuple[str, ...] = (
    'background', 'foreground',
    'card', 'card_foreground',
    'primary', 'primary_foreground',
    'secondary', 'secondary_foreground',
    'muted', 'muted_foreground',
    'accent', 'accent_foreground',
    'gold', 'gold_foreground',
    'ring', 'border', 'input',
    'destructive',
    'live', 'live_foreground',
    'tier_bronze', 'tier_bronze_foreground',
    'tier_silver', 'tier_silver_foreground',
    'win', 'win_foreground',
    'down',
    'chip', 'chip_foreground',
)

DEFAULT_LIGHT: dict[str, str] = {
    'background': '#F3F4FC', 'foreground': '#1A1538',
    'card': '#FFFFFF', 'card_foreground': '#1A1538',
    'primary': '#312783', 'primary_foreground': '#FFFFFF',
    'secondary': '#4338CA', 'secondary_foreground': '#FFFFFF',
    'muted': '#E6E5F7', 'muted_foreground': '#5C5A86',
    'accent': '#5B53D6', 'accent_foreground': '#FFFFFF',
    'gold': '#B8860B', 'gold_foreground': '#FFFFFF',
    'ring': '#312783', 'border': '#C9CBEC', 'input': '#ECEDF8',
    'destructive': '#DC2626',
    'live': '#DC2626', 'live_foreground': '#FFFFFF',
    'tier_bronze': '#92400E', 'tier_bronze_foreground': '#92400E',
    'tier_silver': '#6B7280', 'tier_silver_foreground': '#6B7280',
    'win': '#15924E', 'win_foreground': '#FFFFFF',
    'down': '#DC2626',
    'chip': '#ECEDF8', 'chip_foreground': '#1A1538',
}

DEFAULT_DARK: dict[str, str] = {
    'background': '#0C0820', 'foreground': '#F2F1FB',
    'card': '#191347', 'card_foreground': '#F2F1FB',
    'primary': '#312783', 'primary_foreground': '#FFFFFF',
    'secondary': '#6C63E8', 'secondary_foreground': '#FFFFFF',
    'muted': '#1E1850', 'muted_foreground': '#9D99C8',
    'accent': '#8079EE', 'accent_foreground': '#FFFFFF',
    'gold': '#E6B84C', 'gold_foreground': '#1A1538',
    'ring': '#6C63E8', 'border': 'rgba(255, 255, 255, 0.09)', 'input': '#1E1850',
    'destructive': '#FF6B6B',
    'live': '#FF5260', 'live_foreground': '#FFFFFF',
    'tier_bronze': '#92400E', 'tier_bronze_foreground': '#92400E',
    'tier_silver': '#6B7280', 'tier_silver_foreground': '#6B7280',
    'win': '#36D399', 'win_foreground': '#0C0820',
    'down': '#FF6B6B',
    'chip': '#1E1850', 'chip_foreground': '#F2F1FB',
}


def default_light() -> dict[str, str]:
    return dict(DEFAULT_LIGHT)


def default_dark() -> dict[str, str]:
    return dict(DEFAULT_DARK)
