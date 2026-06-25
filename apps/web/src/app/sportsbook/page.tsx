import Link from 'next/link';
import type { Metadata } from 'next';
import { Card } from '@slyk/ui/components/card';
import { Carousel, CarouselItem } from '@/components/carousel';
import { SportsbookBrowser } from '@/components/sportsbook-browser';
import { apiGet } from '@/lib/config';

export const metadata: Metadata = { title: 'Sportsbook — SLÝKBETS' };

interface EventItem {
  id: string | number;
  name: string;
  sport?: string;
  odds: number;
  odds_draw?: number | null;
  odds_away?: number | null;
  previous_odds?: number | null;
  is_open?: boolean;
  starts_at?: string | null;
}

function isLive(ev: EventItem): boolean {
  return !!ev.starts_at && new Date(ev.starts_at).getTime() <= Date.now();
}

export default async function SportsbookPage() {
  const data = await apiGet<EventItem>('/events/');
  const events = (data.results ?? []) as EventItem[];
  const featured = events.filter((ev) => ev.is_open !== false).slice(0, 8);

  return (
    <div>
      <h1 className="mb-2 text-2xl font-bold">Sportsbook</h1>
      <p className="mb-4 text-muted-foreground">All open markets · live odds update in real time.</p>

      {featured.length > 0 && (
        <Carousel className="mb-6">
          {featured.map((ev) => (
            <CarouselItem key={ev.id} className="w-[220px]">
              <Link href={`/sportsbook/${ev.id}`}>
                <Card className="h-full transition-colors hover:bg-accent/10">
                  <div className="p-4">
                    {isLive(ev) ? (
                      <span className="mb-2 inline-flex items-center gap-1.5 rounded-full bg-live/10 px-2 py-0.5 text-xs font-medium text-live">
                        <span className="h-1.5 w-1.5 rounded-full bg-live animate-pulse" />
                        Live
                      </span>
                    ) : (
                      <span className="mb-2 inline-block text-xs font-medium text-muted-foreground">Upcoming</span>
                    )}
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
