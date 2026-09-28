// Shared sportsbook types and helpers used by the lobby, sportsbook list and event page.

export interface Team {
  id: number;
  name: string;
  logo_url?: string | null;
}

export interface EventItem {
  id: string | number;
  name: string;
  sport?: string;
  odds: number | string;
  odds_draw?: number | string | null;
  odds_away?: number | string | null;
  previous_odds?: number | string | null;
  featured?: boolean;
  is_open?: boolean;
  starts_at?: string | null;
  home_team?: Team | null;
  away_team?: Team | null;
}

export function isLive(ev: Pick<EventItem, 'starts_at'>): boolean {
  if (!ev.starts_at) return false;
  return new Date(ev.starts_at).getTime() <= Date.now();
}

/** Home/away display names, falling back to splitting "A v B" when teams aren't linked. */
export function teamNames(ev: EventItem): { home: string; away: string | null } {
  const [a, b] = ev.name.split(/\s+(?:v|vs\.?)\s+/i);
  return {
    home: ev.home_team?.name ?? a ?? ev.name,
    away: ev.away_team?.name ?? b ?? null,
  };
}

/** Which price columns a market exposes: 1X2, head-to-head (1/2), or a single price. */
export function marketShape(ev: EventItem): '1x2' | '12' | 'single' {
  if (ev.odds_draw != null && ev.odds_away != null) return '1x2';
  if (ev.odds_away != null) return '12';
  return 'single';
}

/** Direction of the last home-price move, used for the ▲/▼ hint on odds buttons. */
export function homeMove(ev: EventItem): 'up' | 'down' | undefined {
  if (ev.previous_odds == null) return undefined;
  const prev = Number(ev.previous_odds);
  const now = Number(ev.odds);
  if (now > prev) return 'up';
  if (now < prev) return 'down';
  return undefined;
}

function sameDay(a: Date, b: Date) {
  return a.getFullYear() === b.getFullYear() && a.getMonth() === b.getMonth() && a.getDate() === b.getDate();
}

/** "Today", "Tomorrow" or "Sat 3 Oct" for a kickoff time. */
export function dayLabel(iso: string): string {
  const d = new Date(iso);
  const today = new Date();
  const tomorrow = new Date();
  tomorrow.setDate(today.getDate() + 1);
  if (sameDay(d, today)) return 'Today';
  if (sameDay(d, tomorrow)) return 'Tomorrow';
  return d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
}

export function kickoffTime(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit', hourCycle: 'h23' });
}

/** Live events first, then soonest kickoff; events with no time go last. */
export function sortEvents<T extends EventItem>(list: T[]): T[] {
  return [...list].sort((a, b) => {
    const la = isLive(a) ? 0 : 1;
    const lb = isLive(b) ? 0 : 1;
    if (la !== lb) return la - lb;
    const ta = a.starts_at ? new Date(a.starts_at).getTime() : Number.MAX_SAFE_INTEGER;
    const tb = b.starts_at ? new Date(b.starts_at).getTime() : Number.MAX_SAFE_INTEGER;
    return ta - tb;
  });
}
