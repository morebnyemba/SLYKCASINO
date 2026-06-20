import type { Metadata } from 'next';
import { LiveFeed } from '@/components/live-feed';
import { BetSlip } from '@/components/bet-slip';
import { apiGet } from '@/lib/config';

// Next 16: route params/searchParams are async — they must be awaited.
type PageProps = {
  params: Promise<{ event: string }>;
  searchParams: Promise<{ outcome?: string }>;
};

export async function generateMetadata({ params }: PageProps): Promise<Metadata> {
  const { event } = await params;
  return { title: `Event ${event} — SLYK Sportsbook` };
}

interface EventDetail {
  name?: string;
  odds?: number;
  odds_draw?: number | null;
  odds_away?: number | null;
}

export default async function EventPage({ params, searchParams }: PageProps) {
  const { event } = await params;
  const { outcome } = await searchParams;
  const data = await apiGet<EventDetail>(`/events/${event}/`);
  const detail = data as EventDetail;
  const name = detail.name || `Event ${event}`;

  let label = name;
  let odds = typeof detail.odds === 'number' ? detail.odds : 1.95;
  if (outcome === 'draw' && detail.odds_draw != null) {
    label = `${name} — Draw`;
    odds = detail.odds_draw;
  } else if (outcome === 'away' && detail.odds_away != null) {
    label = `${name} — Away`;
    odds = detail.odds_away;
  } else if (detail.odds_draw != null) {
    label = `${name} — Home`;
  }

  return (
    <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
      <section>
        <h1 className="mb-2 text-2xl font-bold">{name}</h1>
        <p className="mb-4 text-muted-foreground">Live betting market. Odds update in real time from the Erlang engine.</p>
        <LiveFeed channel={`odds:${event}`} title="Live Odds" height={200} />
      </section>
      <BetSlip event={label} initialOdds={odds} />
    </div>
  );
}
