// Shared sportsbook types and helpers used by the lobby, sportsbook list and event page.

export interface Team {
  id: number;
  name: string;
  logo_url?: string | null;
}

export interface League {
  id: number;
  name: string;
  country?: string;
  logo_url?: string;
  flag_url?: string;
  /** Lower shows first (featured competitions are seeded low). */
  sort_order?: number;
}

/** A market as listings carry it for the market switcher. */
export interface QuickMarket {
  id: number;
  name: string;
  open: boolean;
  outcomes: Record<string, { id: number; label: string; odds: string; open: boolean }>;
}

/** Markets a listing can switch to; `1x2` is the event's own headline prices. */
export const LIST_MARKETS = [
  { id: '1x2', label: '1X2', key: null, cols: [['home', '1'], ['draw', 'X'], ['away', '2']] },
  { id: 'dc', label: 'Double chance', key: 'double_chance:ft', cols: [['1x', '1X'], ['12', '12'], ['x2', 'X2']] },
  { id: 'ou', label: 'Over/Under 2.5', key: 'over_under:ft:2.5', cols: [['over', 'Over'], ['under', 'Under']] },
  { id: 'btts', label: 'Both teams score', key: 'btts:ft', cols: [['yes', 'Yes'], ['no', 'No']] },
] as const;

export type ListMarket = (typeof LIST_MARKETS)[number];

export interface EventItem {
  id: string | number;
  name: string;
  sport?: string;
  odds: number | string;
  odds_draw?: number | string | null;
  odds_away?: number | string | null;
  previous_odds?: number | string | null;
  /** False for feed-imported fixtures until real prices arrive. */
  has_odds?: boolean;
  featured?: boolean;
  is_open?: boolean;
  starts_at?: string | null;
  home_team?: Team | null;
  away_team?: Team | null;
  /** Competition the match belongs to; null for manually created events. */
  league?: League | null;
  /** Provider match status, e.g. 'NS', '1H', 'HT', '2H', 'FT'. */
  status?: string;
  elapsed?: number | null;
  score_home?: number | null;
  score_away?: number | null;
  ht_score_home?: number | null;
  ht_score_away?: number | null;
  /** Trading in play right now (live betting on and the live feed fresh). */
  in_play?: boolean;
  /** Takes bets at all right now (pre-match open, or trading in play). */
  bettable?: boolean;
  /** The 1X2 buttons are live (in play the feed can suspend them on their own). */
  main_open?: boolean;
  /** Open secondary markets (list endpoint). */
  markets_count?: number;
  /** Every market (detail endpoint). */
  markets?: Market[];
  /** List endpoint: the markets the list's market switcher can show, by key. */
  quick_markets?: Record<string, QuickMarket>;
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

/** Whether the 1X2 prices are real (imported fixtures carry a placeholder until priced). */
export function isPriced(ev: Pick<EventItem, 'has_odds'>): boolean {
  return ev.has_odds !== false;
}

/** Whether the event takes bets right now (older APIs: just `is_open`). */
export function isBettable(ev: Pick<EventItem, 'bettable' | 'is_open'>): boolean {
  return ev.bettable ?? ev.is_open !== false;
}

/** Whether the headline 1X2 can be backed right now. */
export function isMainOpen(ev: Pick<EventItem, 'main_open' | 'bettable' | 'is_open'>): boolean {
  return ev.main_open ?? isBettable(ev);
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
export interface LeagueGroup {
  /** Stable key: league id, or 'other' for matches without a league. */
  key: string;
  league: League | null;
  events: EventItem[];
  liveCount: number;
}

/**
 * Cascade matches under their league: featured competitions first (by the
 * league's sort_order), then the rest by country and name, with matches that
 * have no league last. Within a league, live matches come first, then by
 * kick-off (sortEvents).
 */
export function groupByLeague(events: EventItem[]): LeagueGroup[] {
  const groups = new Map<string, LeagueGroup>();
  for (const ev of events) {
    const key = ev.league ? String(ev.league.id) : 'other';
    let g = groups.get(key);
    if (!g) { g = { key, league: ev.league ?? null, events: [], liveCount: 0 }; groups.set(key, g); }
    g.events.push(ev);
    if (isLive(ev)) g.liveCount += 1;
  }
  const label = (l: League) => `${l.country ?? ''} ${l.name}`.trim().toLowerCase();
  return [...groups.values()]
    .map((g) => ({ ...g, events: sortEvents(g.events) }))
    .sort((a, b) => {
      if (!a.league || !b.league) return a.league ? -1 : b.league ? 1 : 0;
      const oa = a.league.sort_order ?? 1000;
      const ob = b.league.sort_order ?? 1000;
      return oa - ob || label(a.league).localeCompare(label(b.league));
    });
}

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

/**
 * Pick the fixtures worth a banner: priced two-team matches that are live and
 * trading, or start within two days, from the highest-ranked leagues first (featured
 * competitions have a low sort_order), live before upcoming, then soonest.
 */
export function pickBannerMatches(events: EventItem[], limit = 4): EventItem[] {
  const horizon = Date.now() + 48 * 3600 * 1000;
  const candidates = events.filter((ev) =>
    isPriced(ev) && !!teamNames(ev).away && (
      // A live match only earns a banner while its prices are actually trading.
      isLive(ev) ? isMainOpen(ev) : !!ev.starts_at && new Date(ev.starts_at).getTime() <= horizon
    ),
  );
  const rank = (ev: EventItem) => ev.league?.sort_order ?? 1000;
  return [...candidates]
    .sort((a, b) =>
      rank(a) - rank(b)
      || Number(isLive(b)) - Number(isLive(a))
      || new Date(a.starts_at ?? 0).getTime() - new Date(b.starts_at ?? 0).getTime())
    .slice(0, limit);
}
