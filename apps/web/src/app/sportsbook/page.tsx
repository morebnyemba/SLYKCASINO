import type { Metadata } from 'next';
import { Suspense } from 'react';
import { AutoRefresh } from '@/components/auto-refresh';
import { SportsbookBrowser } from '@/components/sportsbook-browser';
import { apiGetAll } from '@/lib/config';
import { isLive, isPriced, sortEvents, type EventItem } from '@/lib/sports';

export const metadata: Metadata = { title: 'Sportsbook — BetBlits' };

export default async function SportsbookPage() {
  // Every upcoming/live match, soonest first — the API pages at 25 by default.
  const { rows: all, complete } = await apiGetAll<EventItem>('/events/?upcoming=true&page_size=200');
  // Fixtures the bookmaker hasn't priced yet aren't bettable, so they stay off the board.
  const events = all.filter(isPriced);
  const awaitingOdds = all.length - events.length;
  const open = events.filter((ev) => ev.is_open !== false);
  const featured = sortEvents(open.filter((ev) => ev.featured)).slice(0, 8);
  const topMatches = featured.length > 0 ? featured : sortEvents(open).slice(0, 8);

  return (
    <div>
      {events.some(isLive) && <AutoRefresh seconds={15} />}
      {!complete && (
        <p className="mb-3 rounded-xl border border-border bg-card px-4 py-2.5 text-xs font-semibold text-muted-foreground">
          Some matches couldn’t be loaded right now — refresh in a moment to see the full list.
        </p>
      )}
      {events.length === 0 ? (
        <div className="rounded-2xl border border-border bg-card p-12 text-center">
          <p className="mb-1 font-bold">No markets available yet</p>
          <p className="text-sm text-muted-foreground">
            {awaitingOdds > 0
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
