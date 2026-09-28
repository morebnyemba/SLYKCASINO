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
  /** Provider match status, e.g. 'NS', '1H', 'HT', '2H', 'FT'. */
  status?: string;
  elapsed?: number | null;
  score_home?: number | null;
  score_away?: number | null;
  ht_score_home?: number | null;
  ht_score_away?: number | null;
  /** Open secondary markets (list endpoint). */
  markets_count?: number;
  /** Every market (detail endpoint). */
  markets?: Market[];
  match_facts?: MatchFacts | null;
}

export interface MarketOutcome {
  id: number;
  key: string;
  label: string;
  odds: string | number;
  previous_odds?: string | number | null;
  is_open: boolean;
  result: 'pending' | 'won' | 'lost' | 'void';
}

export type MarketGroup =
  | 'main' | 'goals' | 'halves' | 'handicap' | 'score' | 'teams' | 'corners' | 'cards' | 'scorers' | 'specials';

export interface Market {
  id: number;
  key: string;
  name: string;
  group: MarketGroup;
  kind: string;
  /** What count-based markets count. */
  metric?: 'goals' | 'corners' | 'cards';
  period: 'ft' | '1h' | '2h';
  line?: string | null;
  is_open: boolean;
  settled: boolean;
  outcomes: MarketOutcome[];
}

export const MARKET_GROUPS: { id: MarketGroup; label: string }[] = [
  { id: 'main', label: 'Main' },
  { id: 'goals', label: 'Goals' },
  { id: 'handicap', label: 'Handicaps' },
  { id: 'halves', label: 'Halves' },
  { id: 'teams', label: 'Team' },
  { id: 'scorers', label: 'Goalscorers' },
  { id: 'score', label: 'Correct score' },
  { id: 'corners', label: 'Corners' },
  { id: 'cards', label: 'Cards' },
  { id: 'specials', label: 'Specials' },
];

/** Post-match facts used for settlement (event detail). */
export interface MatchFacts {
  corners?: [number, number];
  yellow?: [number, number];
  red?: [number, number];
  goals?: { minute: number; extra?: number; side: 'home' | 'away'; player: string; own_goal?: boolean; penalty?: boolean }[];
}

const IN_PLAY = new Set(['1H', 'HT', '2H', 'ET', 'BT', 'P', 'SUSP', 'INT', 'LIVE']);
const FINISHED = new Set(['FT', 'AET', 'PEN']);

export function isFinished(ev: Pick<EventItem, 'status'>): boolean {
  return !!ev.status && FINISHED.has(ev.status);
}

export function hasScore(ev: EventItem): boolean {
  return ev.score_home != null && ev.score_away != null;
}

/** "67'", "HT", "FT" — short live clock for a match with a feed status. */
export function matchClock(ev: EventItem): string | null {
  if (!ev.status) return null;
  if (ev.status === 'HT' || FINISHED.has(ev.status)) return ev.status;
  if (IN_PLAY.has(ev.status)) return ev.elapsed != null ? `${ev.elapsed}'` : ev.status;
  return null;
}

/** Swap generic "Home"/"Away" in provider labels for the actual team names. */
export function withTeamNames(text: string, home: string, away: string | null): string {
  return text
    .replace(/\bHome\b/g, home)
    .replace(/\bAway\b/g, away ?? 'Away');
}

export function isLive(ev: Pick<EventItem, 'starts_at' | 'status'>): boolean {
  // A feed status is authoritative when present (e.g. finished matches aren't live).
  if (ev.status) return IN_PLAY.has(ev.status);
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
