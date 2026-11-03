"""The editable color-token schema for the site theme.

Keys mirror the CSS custom properties defined in
`packages/ui/src/styles/globals.css` (minus the `tier-gold*` aliases, which
are computed from `gold`, and `--radius`, which isn't a color). Defaults below
are copied verbatim from that file's `:root` / `[data-theme='dark']` blocks so
seeding this model changes nothing visually until an operator edits it. They're
the BetBlits logo palette: royal blue, cyan→violet and bolt yellow on
indigo navy.
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
    'background': '#F4F6FF', 'foreground': '#0B0C33',
    'card': '#FFFFFF', 'card_foreground': '#0B0C33',
    'primary': '#0046E8', 'primary_foreground': '#FFFFFF',
    'secondary': '#0A55E6', 'secondary_foreground': '#FFFFFF',
    'muted': '#E7E9FB', 'muted_foreground': '#4E5486',
    'accent': '#7A12D6', 'accent_foreground': '#FFFFFF',
    'gold': '#946A00', 'gold_foreground': '#FFFFFF',
    'ring': '#0046E8', 'border': '#D2D6F4',
    'input': '#EDEFFE', 'destructive': '#DC2626',
    'live': '#DC2626', 'live_foreground': '#FFFFFF',
    'tier_bronze': '#92400E', 'tier_bronze_foreground': '#92400E',
    'tier_silver': '#6B7280', 'tier_silver_foreground': '#6B7280',
    'win': '#107A40', 'win_foreground': '#FFFFFF',
    'down': '#DC2626', 'chip': '#EDEFFE',
    'chip_foreground': '#0B0C33', 'sidebar': '#FFFFFF',
    'sidebar_foreground': '#0B0C33', 'odds': '#ECEEFE',
    'odds_hover': '#DCE0FD',
}

DEFAULT_DARK: dict[str, str] = {
    'background': '#101A52', 'foreground': '#F3F4FF',
    'card': '#18246A', 'card_foreground': '#F3F4FF',
    'primary': '#2A5BFF', 'primary_foreground': '#FFFFFF',
    'secondary': '#4FA8FF', 'secondary_foreground': '#050A2E',
    'muted': '#1E2B75', 'muted_foreground': '#BCC3F2',
    'accent': '#C48AFF', 'accent_foreground': '#0A0530',
    'gold': '#FDD508', 'gold_foreground': '#1A1200',
    'ring': '#6F8DFF', 'border': 'rgba(195, 200, 255, 0.16)',
    'input': '#1C2870', 'destructive': '#FF8080',
    'live': '#DC2F3E', 'live_foreground': '#FFFFFF',
    'tier_bronze': '#E39B54', 'tier_bronze_foreground': '#E39B54',
    'tier_silver': '#C7CFDD', 'tier_silver_foreground': '#C7CFDD',
    'win': '#3EE0A0', 'win_foreground': '#04122E',
    'down': '#FF8080', 'chip': '#1E2B75',
    'chip_foreground': '#F3F4FF', 'sidebar': '#0C1446',
    'sidebar_foreground': '#F3F4FF', 'odds': '#22307E',
    'odds_hover': '#2C3B96',
}


def default_light() -> dict[str, str]:
    return dict(DEFAULT_LIGHT)


def default_dark() -> dict[str, str]:
    return dict(DEFAULT_DARK)
