export interface Game {
  id: number;
  slug: string;
  name: string;
  provider: string;
  category?: string;
  rtp: string;
  image_url?: string;
}

export const CASINO_CATEGORIES: { value: string; label: string }[] = [
  { value: 'all', label: 'Lobby' },
  { value: 'crash', label: 'Crash' },
  { value: 'slots', label: 'Slots' },
  { value: 'live', label: 'Live Casino' },
  { value: 'table', label: 'Table Games' },
  { value: 'virtual', label: 'Virtual Sports' },
  { value: 'instant', label: 'Instant Win' },
];

// Crash-category games open the dedicated Aviator-style page, not the slot view.
export function gameHref(game: Game): string {
  if (game.category === 'crash') return '/casino/crash';
  return `/casino/${game.slug}?id=${game.id}`;
}

export const FAVORITES_KEY = 'slyk:favorite-games';

export function loadFavorites(): Set<string> {
  if (typeof window === 'undefined') return new Set();
  try {
    return new Set(JSON.parse(window.localStorage.getItem(FAVORITES_KEY) ?? '[]'));
  } catch {
    return new Set();
  }
}

export function saveFavorites(favs: Set<string>) {
  try {
    window.localStorage.setItem(FAVORITES_KEY, JSON.stringify(Array.from(favs)));
  } catch {
    /* storage may be unavailable */
  }
}

// Deterministic per-slug hash so cosmetic flourishes (tile gradient, "playing now"
// count) stay stable across renders instead of reshuffling on every fetch.
function hashSlug(slug: string): number {
  let h = 0;
  for (let i = 0; i < slug.length; i++) h = (h * 31 + slug.charCodeAt(i)) >>> 0;
  return h;
}

/** Gradient placeholder for games with no operator-supplied artwork. */
export function tileArt(slug: string): string {
  const hue = hashSlug(slug) % 360;
  return `linear-gradient(150deg, hsl(${hue} 58% 30%), hsl(${hue} 64% 12%))`;
}

/** "Players online now" flourish — not backed by real telemetry, just a stable display number. */
export function onlineCount(slug: string): number {
  return 80 + (hashSlug(slug) % 1400);
}

export type GameTag = 'LIVE' | 'HOT' | 'NEW' | null;

/** Derives a badge from real game fields: category, RTP, and recency of id. */
export function gameTag(game: Game, allIds: number[]): GameTag {
  if (game.category === 'live' || game.category === 'crash') return 'LIVE';
  if (parseFloat(game.rtp) >= 97.5) return 'HOT';
  const maxId = allIds.length ? Math.max(...allIds) : game.id;
  if (game.id >= maxId - 2) return 'NEW';
  return null;
}
