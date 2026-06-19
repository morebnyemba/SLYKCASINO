// Cartoon mascot avatar for a game card, deterministic per slug (no API key, no rate limit).
export function gameAvatarUrl(seed: string): string {
  return `https://api.dicebear.com/9.x/bottts/svg?seed=${encodeURIComponent(seed)}&backgroundType=gradientLinear`;
}

// Unsplash hero photos for carousels (stable hotlink IDs, no API key required).
export const CASINO_HERO_IMAGES = [
  'https://images.unsplash.com/photo-1518895949257-7621c3c786d7?w=900&q=80&auto=format', // roulette wheel
  'https://images.unsplash.com/photo-1596731498067-93a4b7174c93?w=900&q=80&auto=format', // slot machine
  'https://images.unsplash.com/photo-1541278107931-e006523892df?w=900&q=80&auto=format', // cards on table
  'https://images.unsplash.com/photo-1606167668584-78701c57f13d?w=900&q=80&auto=format', // poker chips
];
