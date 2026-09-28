import type { Metadata } from 'next';
import { Suspense } from 'react';
import { SportsbookBrowser } from '@/components/sportsbook-browser';
import { apiGet } from '@/lib/config';
import { sortEvents, type EventItem } from '@/lib/sports';

export const metadata: Metadata = { title: 'Sportsbook — SLÝKBETS' };

export default async function SportsbookPage() {
  const data = await apiGet<EventItem>('/events/');
  const events = (data.results ?? []) as EventItem[];
  const open = events.filter((ev) => ev.is_open !== false);
  const featured = sortEvents(open.filter((ev) => ev.featured)).slice(0, 8);
  const topMatches = featured.length > 0 ? featured : sortEvents(open).slice(0, 8);

  return (
    <div>
      {events.length === 0 ? (
        <div className="rounded-2xl border border-border bg-card p-12 text-center">
          <p className="mb-1 font-bold">No markets available yet</p>
          <p className="text-sm text-muted-foreground">Check back soon — new fixtures are added daily.</p>
        </div>
      ) : (
        // SportsbookBrowser reads ?sport / ?tab via useSearchParams.
        <Suspense>
          <SportsbookBrowser events={events} topMatches={topMatches} />
        </Suspense>
      )}
    </div>
  );
}
