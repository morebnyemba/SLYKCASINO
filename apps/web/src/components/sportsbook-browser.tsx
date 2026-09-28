'use client';

import { useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { BsSearch, BsXCircleFill } from 'react-icons/bs';
import { GiTrophyCup } from 'react-icons/gi';
import { SPORT_CATEGORIES } from '@/components/sports-sidebar';
import { Carousel, CarouselItem } from '@/components/carousel';
import { EventRow, FeaturedMatchCard, MarketHeader, sportMeta } from '@/components/event-row';
import { isLive, sortEvents, type EventItem } from '@/lib/sports';

type Tab = 'all' | 'live' | 'upcoming';

export function SportsbookBrowser({ events, topMatches = [], awaitingOdds = 0 }: {
  events: EventItem[];
  topMatches?: EventItem[];
  /** Upcoming fixtures hidden because the bookmaker hasn't priced them yet. */
  awaitingOdds?: number;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const [search, setSearch] = useState('');
  const [searchOpen, setSearchOpen] = useState(false);

  // Sport and tab live in the URL so sidebar links and shared links land on the same view.
  const sport = params.get('sport');
  const tabParam = params.get('tab');
  const tab: Tab = tabParam === 'live' || tabParam === 'upcoming' ? tabParam : 'all';

  function update(next: { sport?: string | null; tab?: Tab }) {
    const q = new URLSearchParams(params.toString());
    if (next.sport !== undefined) {
      if (next.sport) q.set('sport', next.sport); else q.delete('sport');
    }
    if (next.tab !== undefined) {
      if (next.tab !== 'all') q.set('tab', next.tab); else q.delete('tab');
    }
    const qs = q.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }

  // Open matches plus those in play (betting closed, prices locked).
  const openEvents = useMemo(() => sortEvents(events.filter((ev) => ev.is_open !== false || isLive(ev))), [events]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const ev of openEvents) if (ev.sport) c[ev.sport] = (c[ev.sport] ?? 0) + 1;
    return c;
  }, [openEvents]);
  const liveCount = useMemo(() => openEvents.filter(isLive).length, [openEvents]);

  const filtered = useMemo(() => {
    let list = openEvents;
    if (sport) list = list.filter((ev) => ev.sport === sport);
    if (tab === 'live') list = list.filter(isLive);
    if (tab === 'upcoming') list = list.filter((ev) => !isLive(ev));
    const q = search.trim().toLowerCase();
    if (q) {
      list = list.filter((ev) =>
        [ev.name, ev.home_team?.name, ev.away_team?.name].some((s) => s?.toLowerCase().includes(q)),
      );
    }
    return list;
  }, [openEvents, sport, tab, search]);

  // Group by sport, in sidebar order, so each block gets its own 1/X/2 header.
  const groups = useMemo(() => {
    const order = [...SPORT_CATEGORIES.map((c) => c.id), undefined];
    const bySport = new Map<string | undefined, EventItem[]>();
    for (const ev of filtered) {
      const key = SPORT_CATEGORIES.some((c) => c.id === ev.sport) ? ev.sport : undefined;
      bySport.set(key, [...(bySport.get(key) ?? []), ev]);
    }
    return order.filter((k) => bySport.has(k)).map((k) => ({ sport: k, events: bySport.get(k)! }));
  }, [filtered]);

  const tabs: { id: Tab; label: string; count?: number }[] = [
    { id: 'all', label: 'All' },
    { id: 'live', label: 'Live', count: liveCount },
    { id: 'upcoming', label: 'Upcoming' },
  ];

  return (
    <div>
      <section className="min-w-0 space-y-4">
        {topMatches.length > 0 && !sport && tab === 'all' && (
          <div>
            <h2 className="mb-3 text-lg font-extrabold">Top matches</h2>
            <Carousel>
              {topMatches.map((ev) => (
                <CarouselItem key={ev.id}>
                  <FeaturedMatchCard ev={ev} />
                </CarouselItem>
              ))}
            </Carousel>
          </div>
        )}

        {/* Sport chips */}
        <div className="no-scrollbar -mx-3 flex gap-2 overflow-x-auto px-3 sm:mx-0 sm:px-0">
          {[{ id: null as string | null, label: 'All sports', icon: GiTrophyCup }, ...SPORT_CATEGORIES].map((cat) => {
            const Icon = cat.icon;
            const active = sport === cat.id;
            const count = cat.id ? counts[cat.id] ?? 0 : openEvents.length;
            return (
              <button
                key={cat.id ?? 'all'}
                onClick={() => update({ sport: cat.id })}
                className={`flex min-w-[76px] shrink-0 flex-col items-center gap-1.5 rounded-xl border px-3 py-2.5 text-[11.5px] font-bold transition-colors ${
                  active
                    ? 'border-secondary bg-secondary/15 text-foreground'
                    : 'border-border bg-card text-muted-foreground hover:text-foreground'
                } ${count === 0 && !active ? 'opacity-50' : ''}`}
              >
                <span className="relative">
                  <Icon size={22} className={active ? 'text-secondary' : ''} />
                  <span className="absolute -right-3.5 -top-1.5 rounded-full bg-muted px-1 text-[9.5px] font-extrabold text-muted-foreground">
                    {count}
                  </span>
                </span>
                <span className="whitespace-nowrap">{cat.label}</span>
              </button>
            );
          })}
        </div>

        {/* Tabs + search */}
        <div className="sticky top-[var(--header-h)] z-20 -mx-3 flex flex-wrap items-center gap-2 bg-background/95 px-3 py-2 backdrop-blur sm:mx-0 sm:flex-nowrap sm:px-0">
          <div className="flex flex-1 gap-1 rounded-xl border border-border bg-card p-1 sm:flex-none">
            {tabs.map((t) => (
              <button
                key={t.id}
                onClick={() => update({ tab: t.id })}
                className={`flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3.5 py-1.5 text-xs font-bold transition-colors sm:flex-none ${
                  tab === t.id ? 'bg-secondary text-white' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {t.id === 'live' && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-live" />}
                {t.label}
                {t.count != null && t.count > 0 && (
                  <span className={`rounded-full px-1.5 text-[10px] ${tab === t.id ? 'bg-white/20' : 'bg-muted'}`}>{t.count}</span>
                )}
              </button>
            ))}
          </div>
          {/* Phones: search sits behind an icon so the pinned bar stays one row. */}
          <button
            onClick={() => setSearchOpen((v) => !v)}
            aria-label="Search events"
            aria-expanded={searchOpen}
            className={`flex h-10 w-10 shrink-0 items-center justify-center rounded-xl border sm:hidden ${
              searchOpen || search ? 'border-secondary bg-secondary/15 text-foreground' : 'border-border bg-card text-muted-foreground'
            }`}
          >
            <BsSearch size={14} />
          </button>
          <div className={`relative w-full sm:ml-auto sm:block sm:w-64 ${searchOpen || search ? 'block' : 'hidden'}`}>
            <BsSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={13} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search teams or events"
              aria-label="Search events"
              className="w-full rounded-xl border border-border bg-card py-2.5 pl-9 pr-9 text-sm outline-none focus:ring-2 focus:ring-ring"
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                aria-label="Clear search"
                className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground"
              >
                <BsXCircleFill size={13} />
              </button>
            )}
          </div>
        </div>

        {groups.length === 0 && (
          <div className="rounded-2xl border border-border bg-card p-12 text-center">
            <p className="mb-1 font-bold">No matches found</p>
            <p className="mb-4 text-sm text-muted-foreground">
              {tab === 'live' ? 'Nothing is in play right now.' : 'Try another sport or clear your search.'}
            </p>
            {(sport || tab !== 'all' || search) && (
              <button
                onClick={() => { setSearch(''); update({ sport: null, tab: 'all' }); }}
                className="rounded-lg bg-secondary px-4 py-2 text-xs font-bold text-white"
              >
                Show all matches
              </button>
            )}
          </div>
        )}

        {awaitingOdds > 0 && groups.length > 0 && !search && (
          <p className="px-1 text-xs text-muted-foreground">
            {awaitingOdds} more upcoming match{awaitingOdds === 1 ? '' : 'es'} will appear once odds are published.
          </p>
        )}

        {groups.map((g) => {
          const meta = sportMeta(g.sport);
          return (
            <div key={g.sport ?? 'other'} className="overflow-hidden rounded-2xl border border-border bg-card">
              <MarketHeader title={meta.label} icon={meta.icon} count={g.events.length} />
              {g.events.map((ev) => <EventRow key={ev.id} ev={ev} />)}
            </div>
          );
        })}
      </section>

    </div>
  );
}
