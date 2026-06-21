'use client';

import { useMemo, useState } from 'react';
import Link from 'next/link';
import { BsSearch } from 'react-icons/bs';
import { Card } from '@slyk/ui/components/card';
import { buttonVariants } from '@slyk/ui/components/button';
import { LiveFeed } from '@/components/live-feed';
import { SPORT_CATEGORIES, SportsSidebar } from '@/components/sports-sidebar';
import { BetslipCard, BetslipDrawer } from '@/components/betslip-panel';
import { useBetslip, type Selection } from '@/lib/betslip-context';

interface EventItem {
  id: string | number;
  name: string;
  sport?: string;
  odds: number | string;
  odds_draw?: number | string | null;
  odds_away?: number | string | null;
  previous_odds?: number | string | null;
}

/** A tappable price that adds/removes a selection from the shared bet slip. */
function OddsButton({ ev, selection, label, odds }: {
  ev: EventItem; selection: Selection; label: string; odds: number | string;
}) {
  const { isOnSlip, toggleLeg } = useBetslip();
  const active = isOnSlip(ev.id, selection);
  const numericOdds = Number(odds);
  return (
    <button
      onClick={() => toggleLeg({ eventId: ev.id, eventName: ev.name, selection, odds: numericOdds })}
      className={`rounded-md border px-2.5 py-1.5 text-center transition-colors ${
        active
          ? 'border-primary bg-primary text-primary-foreground'
          : 'border-primary/30 bg-primary/5 text-primary hover:bg-primary/10'
      }`}
    >
      <p className={`text-[10px] uppercase ${active ? 'text-primary-foreground/80' : 'text-muted-foreground'}`}>{label}</p>
      <p className="font-mono text-sm font-bold">{numericOdds.toFixed(2)}</p>
    </button>
  );
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
                    <OddsButton ev={ev} selection="home" label="1" odds={ev.odds} />
                    <OddsButton ev={ev} selection="draw" label="X" odds={Number(ev.odds_draw)} />
                    <OddsButton ev={ev} selection="away" label="2" odds={Number(ev.odds_away)} />
                  </div>
                ) : (
                  <div className="flex items-center gap-1">
                    <OddsButton ev={ev} selection="home" label="Odds" odds={ev.odds} />
                    {ev.previous_odds != null && Number(ev.previous_odds) !== Number(ev.odds) && (
                      <span className={`text-xs ${Number(ev.odds) > Number(ev.previous_odds) ? 'text-green-600' : 'text-red-500'}`}>
                        {Number(ev.odds) > Number(ev.previous_odds) ? '▲' : '▼'}
                      </span>
                    )}
                  </div>
                )}
                <Link href={`/sportsbook/${ev.id}`} className={buttonVariants({ size: 'sm', variant: 'outline' })}>
                  More
                </Link>
              </div>
            </Card>
          ))}
        </div>
      </section>

      <aside className="hidden space-y-4 lg:block">
        <BetslipCard />
        <LiveFeed channel="odds" title="Live Odds" height={200} />
      </aside>

      <BetslipDrawer />
    </div>
  );
}
