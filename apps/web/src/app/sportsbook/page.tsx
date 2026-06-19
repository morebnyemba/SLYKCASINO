import Link from 'next/link';
import type { Metadata } from 'next';
import { Card } from '@slyk/ui/components/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@slyk/ui/components/table';
import { buttonVariants } from '@slyk/ui/components/button';
import { Carousel, CarouselItem } from '@/components/carousel';
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
                <Card className="h-full transition-colors hover:bg-accent">
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

      <Card className="p-2">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Event</TableHead>
              <TableHead>Odds</TableHead>
              <TableHead className="text-right">Action</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {events.length === 0 && (
              <TableRow>
                <TableCell colSpan={3} className="text-muted-foreground">No markets available (seed the Django API).</TableCell>
              </TableRow>
            )}
            {events.map((ev) => (
              <TableRow key={ev.id}>
                <TableCell>
                  <span className="mr-2 inline-flex items-center gap-1.5 rounded-full bg-red-500/10 px-2 py-0.5 text-xs font-medium text-red-500">
                    <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" />
                    Live
                  </span>
                  {ev.name}
                </TableCell>
                <TableCell className="font-mono font-semibold">
                  {ev.odds}
                  {ev.previous_odds != null && ev.previous_odds !== ev.odds && (
                    <span className={`ml-1.5 text-xs ${ev.odds > ev.previous_odds ? 'text-green-600' : 'text-red-500'}`}>
                      {ev.odds > ev.previous_odds ? '▲' : '▼'}
                    </span>
                  )}
                </TableCell>
                <TableCell className="text-right">
                  <Link href={`/sportsbook/${ev.id}`} className={buttonVariants({ size: 'sm', variant: 'outline' })}>
                    Bet →
                  </Link>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
