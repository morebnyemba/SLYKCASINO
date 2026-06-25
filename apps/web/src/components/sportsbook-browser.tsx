'use client';

import { useMemo, useState } from 'react';
import { BsSearch } from 'react-icons/bs';
import { LiveFeed } from '@/components/live-feed';
import { SPORT_CATEGORIES, SportsSidebar } from '@/components/sports-sidebar';
import { BetslipCard, BetslipDrawer } from '@/components/betslip-panel';
import { useBetslip, type Selection } from '@/lib/betslip-context';

interface Team {
  id: number;
  name: string;
  logo_url?: string | null;
}

interface EventItem {
  id: string | number;
  name: string;
  sport?: string;
  odds: number | string;
  odds_draw?: number | string | null;
  odds_away?: number | string | null;
  previous_odds?: number | string | null;
  is_open?: boolean;
  starts_at?: string | null;
  home_team?: Team | null;
  away_team?: Team | null;
}

const TABS: { id: 'live' | 'upcoming' | 'all'; label: string }[] = [
  { id: 'live', label: 'Live' },
  { id: 'upcoming', label: 'Upcoming' },
  { id: 'all', label: 'All' },
];

function isLive(ev: EventItem): boolean {
  if (!ev.starts_at) return false;
  return new Date(ev.starts_at).getTime() <= Date.now();
}

function TeamRow({ team, fallback }: { team?: Team | null; fallback: string }) {
  return (
    <div className="flex items-center gap-2 overflow-hidden">
      {team?.logo_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={team.logo_url} alt={team.name} className="h-5 w-5 shrink-0 rounded-full object-cover" />
      ) : (
        <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-chip text-[10px] font-bold text-muted-foreground">
          {(team?.name ?? fallback).charAt(0).toUpperCase()}
        </span>
      )}
      <span className="truncate text-sm font-semibold">{team?.name ?? fallback}</span>
    </div>
  );
}

/** A tappable price that adds/removes a selection from the shared bet slip. */
function OddsButton({ ev, selection, label, odds, move }: {
  ev: EventItem; selection: Selection; label: string; odds: number | string; move?: 'up' | 'down';
}) {
  const { isOnSlip, toggleLeg } = useBetslip();
  const active = isOnSlip(ev.id, selection);
  const numericOdds = Number(odds);
  return (
    <button
      onClick={() => toggleLeg({ eventId: ev.id, eventName: ev.name, selection, odds: numericOdds })}
      className={`flex w-[58px] flex-col items-center gap-0.5 rounded-lg border py-1.5 transition-colors ${
        active ? 'border-secondary bg-secondary text-white' : 'border-border bg-muted/30 text-foreground hover:bg-accent/10'
      }`}
    >
      <span className={`text-[9.5px] font-bold tracking-wide ${active ? 'text-white/80' : 'text-muted-foreground'}`}>{label}</span>
      <span className="flex items-center gap-0.5 font-mono text-sm font-bold">
        {numericOdds.toFixed(2)}
        {move && <span className={`text-[9px] ${move === 'up' ? 'text-win' : 'text-down'}`}>{move === 'up' ? '▲' : '▼'}</span>}
      </span>
    </button>
  );
}

export function SportsbookBrowser({ events }: { events: EventItem[] }) {
  const [search, setSearch] = useState('');
  const [activeId, setActiveId] = useState<string | null>(null);
  const [tab, setTab] = useState<'live' | 'upcoming' | 'all'>('all');

  const openEvents = useMemo(() => events.filter((ev) => ev.is_open !== false), [events]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const cat of SPORT_CATEGORIES) {
      c[cat.id] = openEvents.filter((ev) => ev.sport === cat.id).length;
    }
    return c;
  }, [openEvents]);

  const filtered = useMemo(() => {
    let list = openEvents;
    if (activeId) list = list.filter((ev) => ev.sport === activeId);
    if (tab === 'live') list = list.filter((ev) => isLive(ev));
    if (tab === 'upcoming') list = list.filter((ev) => !isLive(ev));
    if (search) list = list.filter((ev) => ev.name.toLowerCase().includes(search.toLowerCase()));
    return list;
  }, [openEvents, activeId, tab, search]);

  return (
    <div className="grid gap-5 lg:grid-cols-[218px_1fr_320px]">
      <aside className="hidden lg:block">
        <div className="relative mb-3">
          <BsSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={13} />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search events…"
            className="w-full rounded-lg border border-border bg-card py-2.5 pl-8 pr-3 text-sm outline-none focus:ring-2 focus:ring-primary"
          />
        </div>
        <SportsSidebar activeId={activeId} onSelect={setActiveId} counts={counts} />
      </aside>

      <section className="min-w-0">
        <div className="mb-3 lg:hidden">
          <div className="relative">
            <BsSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={13} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search events…"
              className="w-full rounded-lg border border-border bg-card py-2.5 pl-8 pr-3 text-sm outline-none focus:ring-2 focus:ring-primary"
            />
          </div>
        </div>
        <div className="sticky top-20 z-30 -mx-1 mb-4 bg-background px-1 py-2 lg:static lg:mx-0 lg:bg-transparent lg:px-0 lg:py-0">
          <div className="flex items-center justify-end gap-1 rounded-xl border border-border bg-card p-1">
            {TABS.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`flex-1 rounded-lg px-3.5 py-1.5 text-xs font-bold transition-colors lg:flex-none ${
                  tab === t.id ? 'bg-secondary text-white' : 'text-muted-foreground hover:text-foreground'
                }`}
              >
                {t.label}
              </button>
            ))}
          </div>
        </div>

        <div className="space-y-2.5">
          {filtered.length === 0 && (
            <div className="rounded-2xl border border-border bg-card p-12 text-center text-sm text-muted-foreground">
              No markets match your filters.
            </div>
          )}
          {filtered.map((ev) => {
            const live = isLive(ev);
            const prevOdds = ev.previous_odds != null ? Number(ev.previous_odds) : null;
            const homeMove = prevOdds != null ? (Number(ev.odds) > prevOdds ? 'up' : Number(ev.odds) < prevOdds ? 'down' : undefined) : undefined;
            return (
              <div key={ev.id} className="overflow-hidden rounded-2xl border border-border bg-card transition-colors hover:bg-accent/5">
                <div className="flex items-center gap-3.5 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="mb-1.5">
                      {live ? (
                        <span className="inline-flex items-center gap-1.5 rounded-md bg-live/10 px-1.5 py-0.5 text-[10px] font-extrabold text-live">
                          <span className="h-[5px] w-[5px] animate-pulse rounded-full bg-live" /> LIVE
                        </span>
                      ) : ev.starts_at ? (
                        <span className="text-[10.5px] font-bold text-muted-foreground">
                          {new Date(ev.starts_at).toLocaleString(undefined, { weekday: 'short', hour: '2-digit', minute: '2-digit' })}
                        </span>
                      ) : (
                        <span className="text-[10.5px] font-bold text-muted-foreground">Time TBC</span>
                      )}
                    </div>
                    <div className="max-w-[280px] space-y-1">
                      <TeamRow team={ev.home_team} fallback={ev.name.split(' v ')[0] ?? ev.name} />
                      {ev.odds_draw != null && (
                        <TeamRow team={ev.away_team} fallback={ev.name.split(' v ')[1] ?? ''} />
                      )}
                    </div>
                  </div>
                  <div className="flex shrink-0 gap-2">
                    {ev.odds_draw != null ? (
                      <>
                        <OddsButton ev={ev} selection="home" label="1" odds={ev.odds} move={homeMove} />
                        <OddsButton ev={ev} selection="draw" label="X" odds={Number(ev.odds_draw)} />
                        <OddsButton ev={ev} selection="away" label="2" odds={Number(ev.odds_away)} />
                      </>
                    ) : (
                      <OddsButton ev={ev} selection="home" label="ODDS" odds={ev.odds} move={homeMove} />
                    )}
                  </div>
                </div>
              </div>
            );
          })}
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
