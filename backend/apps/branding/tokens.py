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
    'background': '#0E2250', 'foreground': '#F2F6FF',
    'card': '#15306A', 'card_foreground': '#F2F6FF',
    'primary': '#1F66F0', 'primary_foreground': '#FFFFFF',
    'secondary': '#5AAEFF', 'secondary_foreground': '#04122E',
    'muted': '#1B3877', 'muted_foreground': '#B9CBF0',
    'accent': '#46D3FF', 'accent_foreground': '#04122E',
    'gold': '#FDD01E', 'gold_foreground': '#1A1200',
    'ring': '#5AAEFF', 'border': 'rgba(190, 210, 255, 0.16)',
    'input': '#1A3673', 'destructive': '#FF8080',
    'live': '#DC2F3E', 'live_foreground': '#FFFFFF',
    'tier_bronze': '#E39B54', 'tier_bronze_foreground': '#E39B54',
    'tier_silver': '#C7CFDD', 'tier_silver_foreground': '#C7CFDD',
    'win': '#3EE0A0', 'win_foreground': '#04122E',
    'down': '#FF8080', 'chip': '#1B3877',
    'chip_foreground': '#F2F6FF', 'sidebar': '#0B1C44',
    'sidebar_foreground': '#F2F6FF', 'odds': '#1D3D84',
    'odds_hover': '#26499C',
}


def default_light() -> dict[str, str]:
    return dict(DEFAULT_LIGHT)


def default_dark() -> dict[str, str]:
    return dict(DEFAULT_DARK)
