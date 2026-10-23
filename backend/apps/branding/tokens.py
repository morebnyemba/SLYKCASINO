"""The editable color-token schema for the site theme.

Keys mirror the CSS custom properties defined in
`packages/ui/src/styles/globals.css` (minus the `tier-gold*` aliases, which
are computed from `gold`, and `--radius`, which isn't a color). Defaults below
are copied verbatim from that file's `:root` / `[data-theme='dark']` blocks so
seeding this model changes nothing visually until an operator edits it. They're
the BetBlits logo palette: royal blue, cyan and gold on deep navy.
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
    # App shell (header + left nav rail) and odds-button surfaces.
    'sidebar', 'sidebar_foreground',
    'odds', 'odds_hover',
)

DEFAULT_LIGHT: dict[str, str] = {
    'background': '#F2F6FF', 'foreground': '#0A1433',
    'card': '#FFFFFF', 'card_foreground': '#0A1433',
    'primary': '#0149EB', 'primary_foreground': '#FFFFFF',
    'secondary': '#0B5CF0', 'secondary_foreground': '#FFFFFF',
    'muted': '#E2EAFC', 'muted_foreground': '#4D5F8C',
    'accent': '#0A8FD0', 'accent_foreground': '#FFFFFF',
    'gold': '#B07A00', 'gold_foreground': '#FFFFFF',
    'ring': '#0149EB', 'border': '#C7D4F2',
    'input': '#EAF0FE', 'destructive': '#DC2626',
    'live': '#DC2626', 'live_foreground': '#FFFFFF',
    'tier_bronze': '#92400E', 'tier_bronze_foreground': '#92400E',
    'tier_silver': '#6B7280', 'tier_silver_foreground': '#6B7280',
    'win': '#15924E', 'win_foreground': '#FFFFFF',
    'down': '#DC2626', 'chip': '#EAF0FE',
    'chip_foreground': '#0A1433', 'sidebar': '#FFFFFF',
    'sidebar_foreground': '#0A1433', 'odds': '#E8EFFE',
    'odds_hover': '#D8E4FD',
}

DEFAULT_DARK: dict[str, str] = {
    'background': '#060D24', 'foreground': '#EEF3FF',
    'card': '#0D1A3D', 'card_foreground': '#EEF3FF',
    'primary': '#0149EB', 'primary_foreground': '#FFFFFF',
    'secondary': '#1F6FFF', 'secondary_foreground': '#FFFFFF',
    'muted': '#13234D', 'muted_foreground': '#93A6D1',
    'accent': '#0CBBFB', 'accent_foreground': '#031230',
    'gold': '#FDD01E', 'gold_foreground': '#1A1200',
    'ring': '#1F6FFF', 'border': 'rgba(255, 255, 255, 0.09)',
    'input': '#13234D', 'destructive': '#FF6B6B',
    'live': '#FF5260', 'live_foreground': '#FFFFFF',
    'tier_bronze': '#92400E', 'tier_bronze_foreground': '#92400E',
    'tier_silver': '#6B7280', 'tier_silver_foreground': '#6B7280',
    'win': '#36D399', 'win_foreground': '#04122E',
    'down': '#FF6B6B', 'chip': '#13234D',
    'chip_foreground': '#EEF3FF', 'sidebar': '#081430',
    'sidebar_foreground': '#EEF3FF', 'odds': '#15275A',
    'odds_hover': '#1C3473',
}


def default_light() -> dict[str, str]:
    return dict(DEFAULT_LIGHT)


def default_dark() -> dict[str, str]:
    return dict(DEFAULT_DARK)
