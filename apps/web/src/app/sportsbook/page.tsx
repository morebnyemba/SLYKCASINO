import type { Metadata } from 'next';
import { Suspense } from 'react';
import { AutoRefresh } from '@/components/auto-refresh';
import { SportsbookBrowser } from '@/components/sportsbook-browser';
import { SportsbookHero } from '@/components/sportsbook-hero';
import type { Banner } from '@/components/banner-slider';
import { apiGet, apiGetAll } from '@/lib/config';
import { isLive, sortEvents, type EventItem } from '@/lib/sports';
import { SEO_SPORTS, social } from '@/lib/seo';

type PageProps = { searchParams: Promise<{ sport?: string; tab?: string }> };

/** Each sport and the live tab get their own title, description and canonical URL. */
function seoFor(sp: { sport?: string; tab?: string }) {
  const sport = SEO_SPORTS.find((s) => s.id === sp.sport);
  if (sport) {
    return {
      path: `/sportsbook?sport=${sport.id}`,
      h1: `${sport.label} betting odds`,
      title: `${sport.label} Betting Odds — Live & Upcoming Matches`,
      description: `Bet on ${sport.label.toLowerCase()} with the best odds on BetBlits: ${sport.blurb}. In-play betting, `
        + 'cash out and fast EcoCash, OneMoney and InnBucks payouts. 18+.',
    };
  }
  if (sp.tab === 'live') {
    return {
      path: '/sportsbook?tab=live',
      h1: 'Live betting — in-play odds',
      title: 'Live Betting — In-Play Odds & Live Scores',
      description: 'Bet live on matches in play with odds that update every few seconds, live scores and cash out on BetBlits. 18+.',
    };
  }
  return {
    path: '/sportsbook',
    h1: 'Sports betting odds',
    title: 'Sports Betting — Football Odds, Live Betting & Cash Out',
    description: 'Bet on football, basketball, tennis, MMA and more with competitive odds, in-play betting, multi-bet bonuses '
      + 'and cash out on BetBlits. Fast EcoCash, OneMoney and InnBucks deposits. 18+.',
  };
}

export async function generateMetadata({ searchParams }: PageProps): Promise<Metadata> {
  const seo = seoFor(await searchParams);
  return {
    title: seo.title,
    description: seo.description,
    alternates: { canonical: seo.path },
    ...social(seo.title, seo.description, seo.path),
  };
}

export default async function SportsbookPage({ searchParams }: PageProps) {
  const seo = seoFor(await searchParams);
  // Every upcoming/live match with odds, soonest first. Only priced matches are
  // fetched (unpriced ones never show; they're just counted), and the list is
  // cached for 30s and shared by every visitor: live scores and prices reach
  // the page over the realtime socket, not by re-fetching this.
  const [{ rows: events, failed }, unpriced, bannerData] = await Promise.all([
    apiGetAll<EventItem>('/events/?upcoming=true&priced=true&page_size=500', 10, { next: { revalidate: 30 } }),
    apiGet('/events/?upcoming=true&priced=false&page_size=1', { next: { revalidate: 300 } }),
    apiGet<Banner>('/promotions/banners/?placement=sportsbook'),
  ]);
  // Hero: the operator's sportsbook promos (added in the admin).
  // Filter here too, so an API without the placement filter can't leak
  // homepage banners into the sportsbook.
  const banners = ((bannerData.results ?? []) as (Banner & { placement?: string })[])
    .filter((b) => b.placement === 'sportsbook');
  // Fixtures the bookmaker hasn't priced yet aren't bettable, so they stay off the board.
  const awaitingOdds = Number(unpriced.count ?? 0);
  const open = events.filter((ev) => ev.is_open !== false);
  const featured = sortEvents(open.filter((ev) => ev.featured)).slice(0, 8);
  const topMatches = featured.length > 0 ? featured : sortEvents(open).slice(0, 8);

  return (
    <div>
      {/* The visible design has no page heading; this one is for search engines and screen readers. */}
      <h1 className="sr-only">{seo.h1}</h1>
      {/* Fallback for live data when the realtime socket is down; a hiccup fetching the list quietly retries. */}
      {(events.some(isLive) || failed) && <AutoRefresh seconds={failed ? 10 : 30} />}
      {banners.length > 0 && (
        <div className="mb-5">
          <SportsbookHero banners={banners} />
        </div>
      )}
      {events.length === 0 ? (
        <div className="rounded-2xl border border-border bg-card p-12 text-center">
          <p className="mb-1 font-bold">{failed ? 'Getting today’s matches ready' : 'No markets available yet'}</p>
          <p className="text-sm text-muted-foreground">
            {failed
              ? 'The latest fixtures and odds are on their way — this page updates by itself.'
              : awaitingOdds > 0
              ? `${awaitingOdds} upcoming match${awaitingOdds === 1 ? ' is' : 'es are'} waiting for the bookmaker to publish odds.`
              : 'Check back soon — new fixtures are added daily.'}
          </p>
        </div>
      ) : (
        // SportsbookBrowser reads ?sport / ?tab via useSearchParams.
        <Suspense>
          <SportsbookBrowser events={events} topMatches={topMatches} awaitingOdds={awaitingOdds} />
        </Suspense>
      )}
    </div>
  );
}
