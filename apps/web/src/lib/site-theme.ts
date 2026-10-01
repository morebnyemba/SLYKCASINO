import { config } from '@/lib/config';

// Keep in sync with backend/apps/branding/tokens.py TOKEN_KEYS.
const TOKEN_KEYS = [
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
] as const;

// Only literal CSS color syntax — this text is embedded directly into a
// <style> tag, so anything else (url(), comments, `;`/`}`) is rejected.
const COLOR_RE = /^(#[0-9a-fA-F]{3,8}|rgba?\([\d.%,\s]+\)|hsla?\([\d.%,\s]+\))$/;

function toCssBlock(tokens: Record<string, string> | undefined): string {
  if (!tokens) return '';
  const lines: string[] = [];
  for (const key of TOKEN_KEYS) {
    const value = tokens[key];
    if (typeof value === 'string' && COLOR_RE.test(value.trim())) {
      lines.push(`--${key.replace(/_/g, '-')}:${value.trim()};`);
    }
  }
  return lines.join('');
}

/**
 * Fetches the operator-configured site theme and renders it as a CSS
 * override block. Fails silently (empty string) so a backend hiccup never
 * blocks the page — the static defaults in @slyk/ui/globals.css still apply.
 */
export async function fetchSiteThemeCss(): Promise<string> {
  try {
    const res = await fetch(`${config.apiUrl}/branding/theme/`, { next: { revalidate: 10 } });
    if (!res.ok) return '';
    const data = (await res.json()) as { light?: Record<string, string>; dark?: Record<string, string> };
    const light = toCssBlock(data.light);
    const dark = toCssBlock(data.dark);
    if (!light && !dark) return '';
    return `:root{${light}}[data-theme='dark']{${dark}}`;
  } catch {
    return '';
  }
}
