import Link from 'next/link';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { LiveFeed } from '@/components/live-feed';
import { apiGet } from '@/lib/config';

interface EventItem {
  id: string | number;
  name: string;
  odds: number;
}

export default async function LobbyPage() {
  const data = await apiGet<EventItem>('/events/?featured=true');
  const events = (data.results ?? []) as EventItem[];

  return (
    <div className="grid gap-6 lg:grid-cols-[2fr_1fr]">
      <section>
        <h1 className="mb-2 text-2xl font-bold">Lobby</h1>
        <p className="mb-4 text-muted-foreground">Featured live events. Click through to place a bet.</p>
        <div className="grid gap-3">
          {events.length === 0 && (
            <Card>
              <CardContent className="pt-6 text-muted-foreground">
                No events yet (Django API not seeded). Browse the{' '}
                <Link href="/sportsbook" className="text-primary underline-offset-4 hover:underline">sportsbook</Link>.
              </CardContent>
            </Card>
          )}
          {events.map((ev) => (
            <Link key={ev.id} href={`/sportsbook/${ev.id}`}>
              <Card className="transition-colors hover:bg-accent">
                <CardHeader className="flex-row items-center justify-between space-y-0">
                  <CardTitle className="text-base">{ev.name}</CardTitle>
                  <Badge variant="secondary">odds {ev.odds}</Badge>
                </CardHeader>
              </Card>
            </Link>
          ))}
        </div>
      </section>
      <LiveFeed channel="odds" title="Live Odds" />
    </div>
  );
}
