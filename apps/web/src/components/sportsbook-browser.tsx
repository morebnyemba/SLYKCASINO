'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { BsSearch } from 'react-icons/bs';
import { Card } from '@slyk/ui/components/card';
import { buttonVariants } from '@slyk/ui/components/button';
import { LiveFeed } from '@/components/live-feed';
import { SPORT_CATEGORIES, SportsSidebar } from '@/components/sports-sidebar';

interface EventItem {
  id: string | number;
  name: string;
  sport?: string;
  odds: number;
  odds_draw?: number | null;
  odds_away?: number | null;
  previous_odds?: number | null;
}

export function SportsbookBrowser({ events }: { events: EventItem[] }) {
  const [search, setSearch] = useState('');
  const [activeId, setActiveId] = useState<string | null>(null);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const cat of SPORT_CATEGORIES) {
      c[cat.id] = events.filter((ev) => ev.sport === cat.id).length;
    }
    return c;
  }, [events]);

  const filtered = useMemo(() => {
    let list = events;
    if (activeId) list = list.filter((ev) => ev.sport === activeId);
    if (search) list = list.filter((ev) => ev.name.toLowerCase().includes(search.toLowerCase()));
    return list;
  }, [events, activeId, search]);

  return (
    <div className="grid gap-6 lg:grid-cols-[200px_1fr_280px]">
      <aside className="hidden lg:block">
        <div className="relative mb-3">
          <BsSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={13} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search events…"
            className="w-full rounded-md border border-border bg-background py-2 pl-8 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <SportsSidebar activeId={activeId} onSelect={setActiveId} counts={counts} />
      </aside>

      <section>
        <div className="mb-3 lg:hidden">
          <div className="relative">
            <BsSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={13} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search events…"
              className="w-full rounded-md border border-border bg-background py-2 pl-8 pr-3 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
        </div>

        <div className="space-y-2">
          {filtered.length === 0 && (
            <Card className="p-6 text-center text-sm text-muted-foreground">
              No markets match your filters.
            </Card>
          )}
          {filtered.map((ev) => (
            <Card key={ev.id} className="flex items-center justify-between gap-3 p-3 transition-colors hover:bg-accent/10">
              <div className="min-w-0">
                <span className="mb-1 inline-flex items-center gap-1.5 rounded-full bg-red-500/10 px-2 py-0.5 text-[10px] font-medium text-red-500">
                  <span className="h-1.5 w-1.5 rounded-full bg-red-500 animate-pulse" />
                  Live
                </span>
                <p className="truncate font-medium leading-snug">{ev.name}</p>
              </div>
              <div className="flex items-center gap-3 shrink-0">
                {ev.odds_draw != null ? (
                  <div className="flex gap-1.5">
                    <Link href={`/sportsbook/${ev.id}?outcome=home`} className="rounded-md border border-primary/30 bg-primary/5 px-2.5 py-1.5 text-center transition-colors hover:bg-primary/10">
                      <p className="text-[10px] uppercase text-muted-foreground">1</p>
                      <p className="font-mono text-sm font-bold text-primary">{ev.odds}</p>
                    </Link>
                    <Link href={`/sportsbook/${ev.id}?outcome=draw`} className="rounded-md border border-primary/30 bg-primary/5 px-2.5 py-1.5 text-center transition-colors hover:bg-primary/10">
                      <p className="text-[10px] uppercase text-muted-foreground">X</p>
                      <p className="font-mono text-sm font-bold text-primary">{ev.odds_draw}</p>
                    </Link>
                    <Link href={`/sportsbook/${ev.id}?outcome=away`} className="rounded-md border border-primary/30 bg-primary/5 px-2.5 py-1.5 text-center transition-colors hover:bg-primary/10">
                      <p className="text-[10px] uppercase text-muted-foreground">2</p>
                      <p className="font-mono text-sm font-bold text-primary">{ev.odds_away}</p>
                    </Link>
                  </div>
                ) : (
                  <div className="rounded-md border border-primary/30 bg-primary/5 px-3 py-1.5 text-center">
                    <p className="text-[10px] uppercase text-muted-foreground">Odds</p>
                    <p className="font-mono font-bold text-primary">
                      {ev.odds}
                      {ev.previous_odds != null && ev.previous_odds !== ev.odds && (
                        <span className={`ml-1 text-xs ${ev.odds > ev.previous_odds ? 'text-green-600' : 'text-red-500'}`}>
                          {ev.odds > ev.previous_odds ? '▲' : '▼'}
                        </span>
                      )}
                    </p>
                  </div>
                )}
                <Link href={`/sportsbook/${ev.id}`} className={buttonVariants({ size: 'sm' })}>
                  Bet →
                </Link>
              </div>
            </Card>
          ))}
        </div>
      </section>

      <aside className="hidden space-y-4 lg:block">
        <Card className="p-4">
          <p className="mb-2 text-sm font-semibold">Quick links</p>
          <div className="space-y-1.5 text-sm">
            <Link href="/account/bets" className="block rounded-md px-2 py-1.5 text-muted-foreground hover:bg-accent/10 hover:text-foreground">
              My Bets
            </Link>
            <Link href="/account/wallet" className="block rounded-md px-2 py-1.5 text-muted-foreground hover:bg-accent/10 hover:text-foreground">
              Wallet
            </Link>
          </div>
        </Card>
        <LiveFeed channel="odds" title="Live Odds" height={200} />
      </aside>
    </div>
  );
}
