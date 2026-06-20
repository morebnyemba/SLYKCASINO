import Link from 'next/link';
import type { Metadata } from 'next';
import { Card } from '@slyk/ui/components/card';
import { Carousel, CarouselItem } from '@/components/carousel';
import { SportsbookBrowser } from '@/components/sportsbook-browser';
import { apiGet } from '@/lib/config';

export const metadata: Metadata = { title: 'Sportsbook — SLYK' };

interface EventItem {
  id: string | number;
  name: string;
  odds: number;
  previous_odds?: number | null;
}

export default async function SportsbookPage() {
  const data = await apiGet<EventItem>('/events/');
  const events = (data.results ?? []) as EventItem[];

  return (
    <div>
      <h1 className="mb-2 text-2xl font-bold">Sportsbook</h1>
      <p className="mb-4 text-muted-foreground">All open markets. Live odds stream on each event page.</p>

      {events.length > 0 && (
        <Carousel className="mb-6">
          {events.slice(0, 8).map((ev) => (
            <CarouselItem key={ev.id} className="w-[220px]">
              <Link href={`/sportsbook/${ev.id}`}>
                <Card className="h-full transition-colors hover:bg-accent/10">
                  <div className="p-4">
                    <span className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-red-500/10 px-2 py-0.5 text-xs font-medium text-red-500">
                      <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" />
                      Live
                    </span>
                    <p className="font-semibold leading-snug">{ev.name}</p>
                    <p className="mt-2 font-mono text-lg font-bold text-primary">{ev.odds}</p>
                  </div>
                </Card>
              </Link>
            </CarouselItem>
          ))}
        </Carousel>
      )}

      {events.length === 0 ? (
        <Card className="p-6 text-muted-foreground">No markets available (seed the Django API).</Card>
      ) : (
        <SportsbookBrowser events={events} />
      )}
    </div>
  );
}
