import type { Metadata } from 'next';
import Link from 'next/link';
import { LiveFeed } from '@/components/live-feed';
import { AutoRefresh } from '@/components/auto-refresh';
import { EventMarkets } from '@/components/event-markets';
import { apiGet } from '@/lib/config';
import { isLive, type EventItem } from '@/lib/sports';

// Next 16: route params are async — they must be awaited.
type PageProps = {
  params: Promise<{ event: string }>;
};

async function fetchEvent(id: string): Promise<EventItem | null> {
  // Uncached: in play the prices and trading state move by the second.
  const data = (await apiGet<EventItem>(`/events/${id}/`, { next: { revalidate: 0 } })) as Partial<EventItem> & { error?: string };
  if (data.error || data.id == null || !data.name) return null;
  return data as EventItem;
}

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { event } = await params;
  const ev = await fetchEvent(event);
  return { title: `${ev?.name ?? `Event ${event}`} — SLÝKBETS` };
}

export default async function EventPage({ params }: PageProps) {
  const { event } = await params;
  const ev = await fetchEvent(event);

  if (!ev) {
    return (
      <div className="mx-auto max-w-md rounded-2xl border border-border bg-card p-10 text-center">
        <p className="mb-1 font-bold">Match not found</p>
        <p className="mb-5 text-sm text-muted-foreground">It may have finished or been removed from the board.</p>
        <Link href="/sportsbook" className="rounded-lg bg-secondary px-4 py-2 text-sm font-bold text-white">
          Back to sportsbook
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-5xl">
      {isLive(ev) && <AutoRefresh seconds={10} />}
      <section className="min-w-0 space-y-4">
        <EventMarkets ev={ev} />
        <LiveFeed channel={`odds:${event}`} title="Price history" height={200} />
      </section>
    </div>
  );
}
