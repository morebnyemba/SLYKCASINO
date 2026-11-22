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
  /** Ticked in the admin: the league's matches appear on Top Events. */
  top_events?: boolean;
}

/** On the Top Events tab: a featured match, or a match in a league ticked for Top Events. */
export function isTopEvent(ev: { featured?: boolean; league?: League | null }): boolean {
  return !!ev.featured || !!ev.league?.top_events;
}

export type Selection1x2 = 'home' | 'draw' | 'away';

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
  /** Why a match in play isn't taking bets (e.g. "In-play betting closes at 60'"). */
  live_closed?: string | null;
  /** Takes bets at all right now (pre-match open, or trading in play). */
  bettable?: boolean;
  /** The 1X2 buttons are live (in play the feed can suspend them on their own). */
  main_open?: boolean;
  /** In play: 1X2 picks the near-win guard refuses right now (as good as decided), greyed out. */
  main_blocked?: Selection1x2[];
  /** Open secondary markets (list endpoint). */
  markets_count?: number;
  /** O/U, double chance and GG/NG prices for the list's market chips (list endpoint). */
  quick_markets?: Partial<Record<QuickCode, QuickMarket>> | null;
  /** Every market (detail endpoint). */
  markets?: Market[];
  match_facts?: MatchFacts | null;
}

export type QuickCode = 'ou' | 'dc' | 'gg';
/** What a match list shows in its price columns. */
export type ListMarket = '1x2' | QuickCode;

/** Compact list prices: outcomes in the chip's column order, null where an outcome is closed. */
export interface QuickMarket {
  market_id: number;
  line: string | null;
  outcomes: ({ id: number; odds: string } | null)[];
}

/** Market name and outcome labels for a chip's pick (the API leaves them out to stay small). */
export function quickWording(code: QuickCode, line: string | null): { market: string; labels: string[] } {
  if (code === 'ou') return { market: `Total goals ${line ?? ''}`.trim(), labels: [`Over ${line ?? ''}`.trim(), `Under ${line ?? ''}`.trim()] };
  if (code === 'dc') return { market: 'Double chance', labels: ['Home or draw', 'Home or away', 'Draw or away'] };
  return { market: 'Both teams to score', labels: ['Yes', 'No'] };
}

/** The market chips above a match list and the column captions each one shows. */
export const LIST_MARKETS: { id: ListMarket; label: string; cols: string[] }[] = [
  { id: '1x2', label: '1X2', cols: ['1', 'X', '2'] },
  { id: 'ou', label: 'Over/Under', cols: ['Over', 'Under'] },
  { id: 'dc', label: 'DC', cols: ['1X', '12', 'X2'] },
  { id: 'gg', label: 'GG/NG', cols: ['GG', 'NG'] },
];

export function listMarketCols(market: ListMarket) {
  return (LIST_MARKETS.find((m) => m.id === market) ?? LIST_MARKETS[0]).cols;
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
  | 'main' | 'goals' | 'halves' | 'combo' | 'handicap' | 'score' | 'teams' | 'corners' | 'cards' | 'scorers' | 'specials';

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

/** Combined bets ("1 & GG", "Draw & Over 2.5") get their own Combo tab on the match page. */
// Combined bets: result & BTTS, result & total (full time or first half), total & BTTS, HT/FT.
const COMBO_KINDS = new Set(['result_btts', 'result_total', 'total_btts', 'ht_ft']);
export function displayGroup(m: Pick<Market, 'kind' | 'group'>): MarketGroup {
  return COMBO_KINDS.has(m.kind) ? 'combo' : m.group;
}

export const MARKET_GROUPS: { id: MarketGroup; label: string }[] = [
  { id: 'main', label: 'Main' },
  { id: 'goals', label: 'Goals' },
  { id: 'handicap', label: 'Handicaps' },
  { id: 'halves', label: 'Halves' },
  { id: 'combo', label: 'Combo' },
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
  // NR: the feed never sent full time; the match is over, its result still to come.
  if (ev.status === 'NR') return 'Ended';
  if (ev.status === 'HT' || FINISHED.has(ev.status)) return ev.status;
  if (IN_PLAY.has(ev.status)) return ev.elapsed != null ? `${ev.elapsed}'` : ev.status;
  return null;
}

/** Swap generic "Home"/"Away" in provider labels for the actual team names. */
export function withTeamNames(text: string, home: string, away: string | null): string {
  // Feed labels spell it both ways ("Home or draw", "Draw or away").
  return text
    .replace(/\bhome\b/gi, home)
    .replace(/\baway\b/gi, away ?? 'Away');
}

const RESULT_CODE: Record<string, string> = { home: '1', draw: 'X', away: '2' };

/** Betting-shop shorthand for outcomes of many-option markets, where full team
 * names can't fit a button: double chance "1X", result & GG/NG "1 & GG",
 * result & total "X & Over 2.5", half time/full time "1/X". Null = use the label. */
export function shortOutcome(kind: string, key: string, line?: string | null): string | null {
  if (kind === 'double_chance') return ({ '1x': '1X', '12': '12', x2: 'X2' } as Record<string, string>)[key] ?? null;
  const [a, b] = key.split('/');
  if (!RESULT_CODE[a] || !b) return null;
  if (kind === 'result_btts') return b === 'yes' ? `${RESULT_CODE[a]} & GG` : b === 'no' ? `${RESULT_CODE[a]} & NG` : null;
  if (kind === 'result_total' && (b === 'over' || b === 'under')) {
    const n = line != null ? ` ${Number(line)}` : '';
    return `${RESULT_CODE[a]} & ${b === 'over' ? 'Over' : 'Under'}${n}`;
  }
  if (kind === 'ht_ft' && RESULT_CODE[b]) return `${RESULT_CODE[a]}/${RESULT_CODE[b]}`;
  return null;
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
  /** All the league's matches when `events` holds only the rows rendered so far. */
  total?: number;
}

/**
 * Cascade matches under their league: featured competitions first (by the
 * league's sort_order), then the rest by country and name, with matches that
 * have no league last. Within a league, live matches come first, then by
 * kick-off (sortEvents).
 */
/** Only what match lists use, without empty values: every event is embedded in
 * the sportsbook page for the browser, so each byte counts ~600 times. */
const LIST_FIELDS = [
  'id', 'name', 'sport', 'odds', 'odds_draw', 'odds_away', 'previous_odds', 'has_odds', 'featured', 'is_open',
  'starts_at', 'status', 'elapsed', 'score_home', 'score_away', 'markets_count', 'in_play', 'bettable', 'main_open',
  'live_closed', 'main_blocked', 'quick_markets',
] as const;

export function slimEvent(ev: EventItem): EventItem {
  const out: Record<string, unknown> = {};
  for (const k of LIST_FIELDS) {
    const v = (ev as unknown as Record<string, unknown>)[k];
    if (v !== null && v !== undefined && v !== '') out[k] = v;   // booleans and 0 are kept: false means something
  }
  const team = (t?: Team | null) => (t ? { id: t.id, name: t.name, ...(t.logo_url ? { logo_url: t.logo_url } : {}) } : undefined);
  if (ev.home_team) out.home_team = team(ev.home_team);
  if (ev.away_team) out.away_team = team(ev.away_team);
  if (ev.league) {
    const { id, name, country, logo_url, flag_url, sort_order } = ev.league;
    const top_events = ev.league.top_events || undefined;   // only sent when ticked (bytes ×600)
    out.league = Object.fromEntries(Object.entries({ id, name, country, logo_url, flag_url, sort_order, top_events })
      .filter(([, v]) => v !== null && v !== undefined && v !== ''));
  }
  return out as unknown as EventItem;
}

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
