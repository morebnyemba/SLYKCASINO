// Search-engine helpers shared by metadata, the sitemap and structured data.
// Server-safe (no client components or icons imported here).
import { config } from '@/lib/config';
import type { EventItem } from '@/lib/sports';

/** Absolute site origin, e.g. https://betblits.com (no trailing slash). */
export const SITE_URL = (process.env.NEXT_PUBLIC_SITE_URL || config.siteUrl || 'http://localhost').replace(/\/$/, '');

export const absolute = (path: string) => `${SITE_URL}${path.startsWith('/') ? path : `/${path}`}`;

/** Sports with their own landing view (/sportsbook?sport=<id>), for titles and the sitemap. */
export const SEO_SPORTS: { id: string; label: string; blurb: string }[] = [
  { id: 'football', label: 'Football', blurb: 'Premier League, PSL, Champions League and leagues worldwide' },
  { id: 'basketball', label: 'Basketball', blurb: 'NBA, EuroLeague and more' },
  { id: 'tennis', label: 'Tennis', blurb: 'ATP, WTA and Grand Slams' },
  { id: 'mma', label: 'MMA', blurb: 'UFC and the biggest fight cards' },
  { id: 'boxing', label: 'Boxing', blurb: 'title fights and undercards' },
  { id: 'baseball', label: 'Baseball', blurb: 'MLB and international baseball' },
  { id: 'athletics', label: 'Athletics', blurb: 'track and field events' },
  { id: 'esports', label: 'Esports', blurb: 'CS2, Dota 2, League of Legends and more' },
];

export const sportLabel = (id?: string | null) => SEO_SPORTS.find((s) => s.id === id)?.label;

export const DEFAULT_DESCRIPTION =
  'Bet on football, basketball, tennis and more with live odds, in-play betting and cash out — plus BetBlits Aviator. '
  + 'Fast EcoCash, OneMoney and InnBucks deposits and payouts. 18+, play responsibly.';

/** Paths that must never appear in search results (private or transactional). */
export const PRIVATE_PATHS = [
  '/account', '/deposit', '/play/', '/livechat', '/forgot-password', '/reset-password', '/verify-email',
  '/admin-portal', '/api/',
];

export const noIndex = { robots: { index: false, follow: false, nocache: true } } as const;

function teams(ev: EventItem): [string, string] | null {
  if (ev.home_team?.name && ev.away_team?.name) return [ev.home_team.name, ev.away_team.name];
  const parts = ev.name.split(/\s+(?:vs\.?|v)\s+/i);
  return parts.length === 2 ? [parts[0], parts[1]] : null;
}

const kickoff = (iso?: string | null) => (iso
  ? new Date(iso).toLocaleString('en-GB', { weekday: 'short', day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit', timeZone: 'Africa/Harare' })
  : '');

/** "Man Utd vs Arsenal Betting Odds — Premier League" style title for a match. */
export function eventTitle(ev: EventItem): string {
  const comp = ev.league?.name ? ` — ${ev.league.name}` : '';
  return `${ev.name} Betting Odds${comp}`;
}

export function eventDescription(ev: EventItem): string {
  const t = teams(ev);
  const when = kickoff(ev.starts_at);
  const odds = [ev.odds, ev.odds_draw, ev.odds_away].map((o) => (o == null ? null : Number(o)));
  const priced = ev.has_odds !== false && odds[0];
  const price = priced && t
    ? ` ${t[0]} ${odds[0]!.toFixed(2)}${odds[1] ? `, draw ${odds[1].toFixed(2)}` : ''}${odds[2] ? `, ${t[1]} ${odds[2].toFixed(2)}` : ''}.`
    : '';
  const markets = ev.markets_count || ev.markets?.length;
  return `${ev.name}${ev.league?.name ? ` (${ev.league.name})` : ''}${when ? `, ${when} CAT` : ''}: compare odds and bet live.${price}`
    + `${markets ? ` ${markets}+ markets including goals, handicaps and correct score.` : ''} Cash out any time on BetBlits.`;
}

const STATUS = (s?: string) => {
  if (!s || s === 'NS' || s === 'TBD') return 'https://schema.org/EventScheduled';
  if (['PST'].includes(s)) return 'https://schema.org/EventPostponed';
  if (['CANC', 'ABD', 'AWD', 'WO'].includes(s)) return 'https://schema.org/EventCancelled';
  return 'https://schema.org/EventScheduled';
};

/** schema.org SportsEvent + BreadcrumbList for a match page. */
export function eventJsonLd(ev: EventItem): object[] {
  const t = teams(ev);
  const url = absolute(`/sportsbook/${ev.id}`);
  const sport = sportLabel(ev.sport);
  const event: Record<string, unknown> = {
    '@context': 'https://schema.org',
    '@type': 'SportsEvent',
    name: ev.name,
    url,
    description: eventDescription(ev),
    eventStatus: STATUS(ev.status),
    eventAttendanceMode: 'https://schema.org/OfflineEventAttendanceMode',
    ...(ev.starts_at ? { startDate: ev.starts_at } : {}),
    ...(sport ? { sport } : {}),
    ...(ev.league?.name ? { superEvent: { '@type': 'SportsEvent', name: ev.league.name } } : {}),
    ...(t ? {
      homeTeam: { '@type': 'SportsTeam', name: t[0], ...(ev.home_team?.logo_url ? { logo: ev.home_team.logo_url } : {}) },
      awayTeam: { '@type': 'SportsTeam', name: t[1], ...(ev.away_team?.logo_url ? { logo: ev.away_team.logo_url } : {}) },
      competitor: [{ '@type': 'SportsTeam', name: t[0] }, { '@type': 'SportsTeam', name: t[1] }],
    } : {}),
    location: { '@type': 'Place', name: ev.league?.country || 'TBA' },
    organizer: { '@type': 'Organization', name: 'BetBlits', url: SITE_URL },
  };
  const crumbs = [
    { name: 'Sportsbook', item: absolute('/sportsbook') },
    ...(sport ? [{ name: sport, item: absolute(`/sportsbook?sport=${ev.sport}`) }] : []),
    { name: ev.name, item: url },
  ];
  return [event, {
    '@context': 'https://schema.org',
    '@type': 'BreadcrumbList',
    itemListElement: crumbs.map((c, i) => ({ '@type': 'ListItem', position: i + 1, ...c })),
  }];
}

/** Organization + WebSite structured data for every page. */
export function siteJsonLd(siteName: string, logo?: string): object[] {
  return [
    {
      '@context': 'https://schema.org',
      '@type': 'Organization',
      name: siteName,
      url: SITE_URL,
      logo: logo || absolute('/icons/icon-512.png'),
    },
    {
      '@context': 'https://schema.org',
      '@type': 'WebSite',
      name: siteName,
      url: SITE_URL,
      inLanguage: 'en',
    },
  ];
}

/** Renders JSON-LD safely (escapes "<" so a team name can't close the script tag). */
export function jsonLdHtml(data: object | object[]): string {
  return JSON.stringify(data).replace(/</g, '\\u003c');
}

/**
 * Page-level Open Graph / Twitter metadata. Next replaces (doesn't merge) these
 * objects per page, so every page passes the shared fields again here.
 */
export function social(title: string, description: string, path: string, image = '/opengraph-image') {
  return {
    openGraph: {
      type: 'website' as const, siteName: 'BetBlits', locale: 'en_ZW', title, description, url: path,
      images: [{ url: image, width: 1200, height: 630, alt: title }],
    },
    twitter: { card: 'summary_large_image' as const, title, description, images: [image] },
  };
}
