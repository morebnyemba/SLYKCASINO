/** Shapes and helpers for the operator sportsbook screens. */

export interface TeamRef { id: number; name: string; logo_url: string }
export interface LeagueRef { id: number; name: string; country: string; flag_url: string; logo_url: string }

export type MatchState = 'upcoming' | 'started' | 'live' | 'finished' | 'void';

export interface AdminMatch {
  id: number;
  name: string;
  sport: string;
  provider: string;
  external_id: string | null;
  source: 'feed' | 'manual';
  state: MatchState;
  trading: { in_play: boolean; bettable: boolean; main_open: boolean };
  league: number | null;
  league_detail: LeagueRef | null;
  home_team: TeamRef | null;
  away_team: TeamRef | null;
  starts_at: string | null;
  status: string;
  elapsed: number | null;
  score_home: number | null;
  score_away: number | null;
  ht_score_home: number | null;
  ht_score_away: number | null;
  odds: string;
  odds_draw: string | null;
  odds_away: string | null;
  previous_odds: string | null;
  has_odds: boolean;
  prices_locked: boolean;
  featured: boolean;
  is_open: boolean;
  markets_count: number;
  bets_count: number;
}

export interface Paged<T> { count: number; next: string | null; previous: string | null; results: T[] }

export interface AdminLeague {
  id: number;
  provider: string;
  league_id: number;
  name: string;
  country: string;
  logo_url: string;
  flag_url: string;
  enabled: boolean;
  sort_order: number;
  upcoming_count: number;
}

export const SPORTS = [
  { id: 'football', label: 'Football' },
  { id: 'basketball', label: 'Basketball' },
  { id: 'tennis', label: 'Tennis' },
  { id: 'mma', label: 'MMA' },
  { id: 'boxing', label: 'Boxing' },
  { id: 'baseball', label: 'Baseball' },
  { id: 'athletics', label: 'Athletics' },
  { id: 'esports', label: 'Esports' },
];

/** api-football style status codes an operator can set by hand. */
export const STATUSES = [
  { id: '', label: 'Not started' },
  { id: 'NS', label: 'NS · Not started' },
  { id: '1H', label: '1H · First half' },
  { id: 'HT', label: 'HT · Half-time' },
  { id: '2H', label: '2H · Second half' },
  { id: 'ET', label: 'ET · Extra time' },
  { id: 'P', label: 'P · Penalties' },
  { id: 'FT', label: 'FT · Full time' },
  { id: 'AET', label: 'AET · After extra time' },
  { id: 'PEN', label: 'PEN · After penalties' },
  { id: 'PST', label: 'PST · Postponed' },
  { id: 'SUSP', label: 'SUSP · Suspended' },
  { id: 'CANC', label: 'CANC · Cancelled' },
  { id: 'ABD', label: 'ABD · Abandoned' },
];

export function teamNames(m: Pick<AdminMatch, 'name' | 'home_team' | 'away_team'>) {
  if (m.home_team || m.away_team) return { home: m.home_team?.name ?? '—', away: m.away_team?.name ?? '—' };
  const [home, away] = m.name.split(/\s+(?:v|vs\.?)\s+/i);
  return { home: home ?? m.name, away: away ?? '' };
}

export function kickoff(iso: string | null, opts: { withDay?: boolean } = { withDay: true }) {
  if (!iso) return 'TBC';
  const d = new Date(iso);
  const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  if (!opts.withDay) return time;
  const today = new Date();
  const tomorrow = new Date(today.getFullYear(), today.getMonth(), today.getDate() + 1);
  const same = (a: Date, b: Date) => a.toDateString() === b.toDateString();
  const day = same(d, today) ? 'Today' : same(d, tomorrow) ? 'Tomorrow'
    : d.toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
  return `${day} · ${time}`;
}

/** <input type="datetime-local"> value from an ISO string, in local time. */
export function toLocalInput(iso: string | null) {
  if (!iso) return '';
  const d = new Date(iso);
  const pad = (n: number) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

export function fromLocalInput(v: string) {
  return v ? new Date(v).toISOString() : null;
}
