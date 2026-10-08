import { MARKET_GROUPS, type Market } from '@/lib/sports';

/** Lower-case, accents stripped, punctuation folded to spaces — so "Mbappé" finds
 * "mbappe" and "o/u" finds "o u". Dots stay for lines like 2.5. */
export function normalize(text: string): string {
  return text
    .normalize('NFD')
    .replace(/[̀-ͯ]/g, '')
    .toLowerCase()
    .replace(/[^a-z0-9.+-]+/g, ' ')
    .trim();
}

export function searchTokens(query: string): string[] {
  return normalize(query).split(' ').filter(Boolean);
}

/** Shorthand punters type, keyed by market kind / period. */
const KIND_WORDS: Record<string, string> = {
  match_result: '1x2 result winner win',
  double_chance: 'dc 1x 12 x2 double chance',
  draw_no_bet: 'dnb draw no bet',
  over_under: 'ou o u over under totals goals',
  home_over_under: 'ou over under totals team goals',
  away_over_under: 'ou over under totals team goals',
  btts: 'btts gg ng both teams to score goal goal',
  asian_handicap: 'ah asian handicap',
  handicap_result: 'eh european handicap',
  correct_score: 'cs correct exact score',
  exact_goals: 'exact goals number',
  odd_even: 'odd even',
  ht_ft: 'htft ht ft half time full time',
  result_btts: 'btts gg result both teams',
  result_total: 'result total over under',
  anytime_scorer: 'goalscorer scorer player anytime',
  first_scorer: 'goalscorer scorer player first',
  last_scorer: 'goalscorer scorer player last',
  clean_sheet_home: 'clean sheet',
  clean_sheet_away: 'clean sheet',
  win_to_nil_home: 'win to nil',
  win_to_nil_away: 'win to nil',
  win_to_nil: 'win to nil',
  red_card: 'red card',
};
const PERIOD_WORDS: Record<string, string> = {
  '1h': '1h ht first half 1st half',
  '2h': '2h second half 2nd half',
  ft: 'ft full time',
};
const GROUP_LABEL = Object.fromEntries(MARKET_GROUPS.map((g) => [g.id, g.label]));

function has(text: string, tokens: string[]) {
  return tokens.every((t) => text.includes(t));
}

/** The words a market is findable by, apart from its outcomes. */
export function marketText(m: Market, name: string): string {
  return normalize([
    name, GROUP_LABEL[m.group] ?? '', KIND_WORDS[m.kind] ?? '', PERIOD_WORDS[m.period] ?? '', m.metric ?? '',
  ].join(' '));
}

/**
 * Narrow a market to what the query asks for. Returns the market whole when its
 * name/type matches; otherwise only the outcomes (or, for line markets, the line)
 * that complete the match — "over 2.5" keeps the 2.5 line of Total goals, a
 * player's name keeps that player in the scorer lists. Null when nothing fits.
 */
export function filterMarket(
  m: Market, tokens: string[], names: (text: string) => string, lineText = '',
): Market | null {
  if (!tokens.length) return m;
  const head = `${marketText(m, names(m.name))} ${normalize(lineText)}`;
  if (has(head, tokens)) return m;
  const outcomes = m.outcomes.filter((o) => has(`${head} ${normalize(names(o.label))}`, tokens));
  return outcomes.length ? { ...m, outcomes } : null;
}
