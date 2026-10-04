'use client';

import { useCallback, useEffect, useMemo, useState } from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { BsArrowDownUp, BsChevronDown, BsLightningChargeFill } from 'react-icons/bs';
import { GiTrophyCup } from 'react-icons/gi';
import { SPORT_CATEGORIES } from '@/components/sports-sidebar';
import { Carousel, CarouselItem } from '@/components/carousel';
import { EventRow, FeaturedMatchCard, MarketHeader, sportMeta } from '@/components/event-row';
import { LeagueSection } from '@/components/league-section';
import { groupByLeague, isLive, sortEvents, type EventItem } from '@/lib/sports';

type Tab = 'live' | 'top' | 'upcoming' | 'countries';
type SortMode = 'league' | 'time';

const COLLAPSED_KEY = 'slyk:collapsed-leagues';
/** ⚡ "Starting soon": kick-off within this window. */
const SOON_MS = 3 * 3600 * 1000;
const NO_COUNTRY = 'International';

const TABS: { id: Tab; label: string }[] = [
  { id: 'live', label: 'Live' },
  { id: 'top', label: 'Top Events' },
  { id: 'upcoming', label: 'Upcoming' },
  { id: 'countries', label: 'Countries' },
];

/** Local calendar day of a kick-off, e.g. "2026-10-03" (the viewer's timezone). */
function localDay(value: string | Date) {
  const d = new Date(value);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function dayOptionLabel(day: string, today: string, tomorrow: string) {
  if (day === today) return 'Today';
  if (day === tomorrow) return 'Tomorrow';
  const [y, m, d] = day.split('-').map(Number);
  return new Date(y, m - 1, d).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
}

/** A native select dressed as a filter pill (native keeps it fast and thumb-friendly on phones). */
function FilterSelect({ value, onChange, label, icon, children }: {
  value: string;
  onChange: (v: string) => void;
  label: string;
  icon?: React.ReactNode;
  children: React.ReactNode;
}) {
  return (
    <div className="relative min-w-0 flex-1">
      {icon && <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2">{icon}</span>}
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        aria-label={label}
        className={`h-11 w-full appearance-none truncate rounded-xl border border-border bg-card pr-7 text-[13px] font-semibold text-foreground outline-none focus:ring-2 focus:ring-ring sm:text-sm ${icon ? 'pl-9' : 'pl-3'}`}
      >
        {children}
      </select>
      <BsChevronDown size={11} className="pointer-events-none absolute right-2.5 top-1/2 -translate-y-1/2 text-muted-foreground" />
    </div>
  );
}

export function SportsbookBrowser({ events, topMatches = [], awaitingOdds = 0 }: {
  events: EventItem[];
  topMatches?: EventItem[];
  /** Upcoming fixtures hidden because the bookmaker hasn't priced them yet. */
  awaitingOdds?: number;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();

  // Everything lives in the URL so sidebar links and shared links land on the same view.
  const sport = params.get('sport');
  const tabParam = params.get('tab');
  const tab: Tab = TABS.some((t) => t.id === tabParam) ? (tabParam as Tab) : 'upcoming';
  const day = params.get('day');
  const sort: SortMode = params.get('sort') === 'time' ? 'time' : 'league';
  const soon = params.get('soon') === '1';

  // Days depend on the viewer's timezone, so they're built after mount (the
  // server can't know it, and a mismatch would break hydration).
  const [mounted, setMounted] = useState(false);
  useEffect(() => { setMounted(true); }, []);

  function update(next: { sport?: string | null; tab?: Tab; day?: string | null; sort?: SortMode; soon?: boolean }) {
    const q = new URLSearchParams(params.toString());
    const set = (key: string, value: string | null) => { if (value) q.set(key, value); else q.delete(key); };
    if (next.sport !== undefined) set('sport', next.sport);
    if (next.tab !== undefined) set('tab', next.tab === 'upcoming' ? null : next.tab);
    if (next.day !== undefined) set('day', next.day);
    if (next.sort !== undefined) set('sort', next.sort === 'time' ? 'time' : null);
    if (next.soon !== undefined) set('soon', next.soon ? '1' : null);
    const qs = q.toString();
    router.replace(qs ? `${pathname}?${qs}` : pathname, { scroll: false });
  }

  // Open matches plus those in play (betting closed, prices locked).
  const openEvents = useMemo(() => sortEvents(events.filter((ev) => ev.is_open !== false || isLive(ev))), [events]);
  const liveCount = useMemo(() => openEvents.filter(isLive).length, [openEvents]);
  const sportCounts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const ev of openEvents) if (ev.sport) c[ev.sport] = (c[ev.sport] ?? 0) + 1;
    return c;
  }, [openEvents]);

  const days = useMemo(() => {
    if (!mounted) return [];
    const now = new Date();
    const today = localDay(now);
    const tomorrow = localDay(new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1));
    const counts = new Map<string, number>();
    for (const ev of openEvents) {
      if (!ev.starts_at || isLive(ev) || (sport && ev.sport !== sport)) continue;
      const d = localDay(ev.starts_at);
      counts.set(d, (counts.get(d) ?? 0) + 1);
    }
    return [...counts.entries()].sort(([a], [b]) => a.localeCompare(b)).slice(0, 10)
      .map(([d, count]) => ({ day: d, count, label: dayOptionLabel(d, today, tomorrow) }));
  }, [mounted, openEvents, sport]);

  const filtered = useMemo(() => {
    let list = openEvents;
    if (sport) list = list.filter((ev) => ev.sport === sport);
    if (tab === 'live') return list.filter(isLive);
    if (tab === 'upcoming') list = list.filter((ev) => !isLive(ev));
    if (tab === 'top') {
      // Featured matches and featured competitions (leagues ranked in the admin).
      const top = list.filter((ev) => ev.featured || (ev.league?.sort_order ?? 1000) < 1000);
      list = top.length > 0 ? top : list.slice(0, 30);
    }
    if (mounted && day) list = list.filter((ev) => !isLive(ev) && !!ev.starts_at && localDay(ev.starts_at) === day);
    if (mounted && soon) {
      const now = Date.now();
      list = list.filter((ev) => {
        const t = ev.starts_at ? new Date(ev.starts_at).getTime() : NaN;
        return !isLive(ev) && t >= now && t - now <= SOON_MS;
      });
    }
    return list;
  }, [openEvents, sport, tab, day, soon, mounted]);

  // One block per sport, in sidebar order, each with its own 1/X/2 header.
  const groups = useMemo(() => {
    const order = [...SPORT_CATEGORIES.map((c) => c.id), undefined];
    const bySport = new Map<string | undefined, EventItem[]>();
    for (const ev of filtered) {
      const key = SPORT_CATEGORIES.some((c) => c.id === ev.sport) ? ev.sport : undefined;
      bySport.set(key, [...(bySport.get(key) ?? []), ev]);
    }
    return order.filter((k) => bySport.has(k)).map((k) => {
      const list = bySport.get(k)!;
      return { sport: k, events: list, leagues: groupByLeague(list) };
    });
  }, [filtered]);

  // Countries tab: country -> its leagues, featured competitions first.
  const countries = useMemo(() => {
    if (tab !== 'countries') return [];
    const byCountry = new Map<string, { name: string; flag?: string; events: EventItem[]; rank: number }>();
    for (const ev of filtered) {
      const name = ev.league?.country || NO_COUNTRY;
      let c = byCountry.get(name);
      if (!c) { c = { name, events: [], rank: 1000 }; byCountry.set(name, c); }
      c.events.push(ev);
      c.flag ??= ev.league?.flag_url || undefined;
      c.rank = Math.min(c.rank, ev.league?.sort_order ?? 1000);
    }
    return [...byCountry.values()]
      .sort((a, b) => (a.name === NO_COUNTRY ? 1 : 0) - (b.name === NO_COUNTRY ? 1 : 0)
        || a.rank - b.rank || a.name.localeCompare(b.name))
      .map((c) => ({ ...c, leagues: groupByLeague(c.events) }));
  }, [tab, filtered]);
  const [openCountries, setOpenCountries] = useState<Set<string>>(new Set());
  const toggleCountry = (name: string) => setOpenCountries((prev) => {
    const next = new Set(prev);
    if (next.has(name)) next.delete(name); else next.add(name);
    return next;
  });

  // Collapsed leagues are remembered per browser.
  const [collapsed, setCollapsed] = useState<Set<string>>(new Set());
  useEffect(() => {
    try {
      const saved = JSON.parse(localStorage.getItem(COLLAPSED_KEY) ?? '[]');
      if (Array.isArray(saved)) setCollapsed(new Set(saved.map(String)));
    } catch { /* storage unavailable */ }
  }, []);
  const toggleLeague = useCallback((key: string) => {
    setCollapsed((prev) => {
      const next = new Set(prev);
      if (next.has(key)) next.delete(key); else next.add(key);
      try { localStorage.setItem(COLLAPSED_KEY, JSON.stringify([...next])); } catch { /* ignore */ }
      return next;
    });
  }, []);

  const SportIcon = sport ? sportMeta(sport).icon ?? GiTrophyCup : GiTrophyCup;
  const filtersActive = !!(sport || day || soon);
  const empty = tab === 'countries' ? countries.length === 0 : groups.length === 0;

  const leagueSections = (leagues: ReturnType<typeof groupByLeague>, prefix: string, fallbackTitle: string) =>
    leagues.map((lg) => {
      const key = `${prefix}:${lg.key}`;
      return (
        <LeagueSection
          key={key}
          group={lg}
          collapsed={collapsed.has(key)}
          onToggle={() => toggleLeague(key)}
          fallbackTitle={fallbackTitle}
        />
      );
    });

  return (
    <section className="min-w-0 space-y-4">
      {topMatches.length > 0 && tab === 'upcoming' && !filtersActive && (
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

      {/* View tabs + filters, pinned under the header while scrolling. */}
      <div className="sticky top-[var(--header-h)] z-20 -mx-3 space-y-2.5 border-b border-border bg-background/95 px-3 pb-3 pt-2 backdrop-blur sm:mx-0 sm:px-0">
        <div className="grid grid-cols-4 gap-2" role="tablist" aria-label="Sportsbook view">
          {TABS.map((t) => (
            <button
              key={t.id}
              role="tab"
              aria-selected={tab === t.id}
              onClick={() => update({ tab: t.id, ...(t.id === 'live' ? { day: null, soon: false } : {}) })}
              className={`relative flex h-11 items-center justify-center gap-1.5 rounded-xl px-1 text-[13px] font-bold transition-colors sm:text-sm ${
                tab === t.id ? 'bg-secondary text-white shadow' : 'bg-muted/70 text-foreground hover:bg-muted'
              }`}
            >
              {t.id === 'live' && liveCount > 0 && <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-live" />}
              <span className="truncate">{t.label}</span>
            </button>
          ))}
        </div>

        <div className="flex gap-2">
          <FilterSelect
            label="Sport"
            value={sport ?? ''}
            onChange={(v) => update({ sport: v || null })}
            icon={<SportIcon size={17} className="text-secondary" />}
          >
            <option value="">All</option>
            {SPORT_CATEGORIES.filter((c) => (sportCounts[c.id] ?? 0) > 0 || sport === c.id).map((c) => (
              <option key={c.id} value={c.id}>{c.label}</option>
            ))}
          </FilterSelect>
          {tab !== 'live' && (
            <FilterSelect label="Day" value={day ?? ''} onChange={(v) => update({ day: v || null })}>
              <option value="">All days</option>
              {days.map((d) => <option key={d.day} value={d.day}>{d.label}</option>)}
              {day && !days.some((d) => d.day === day) && <option value={day}>{day}</option>}
            </FilterSelect>
          )}
          {tab !== 'countries' && (
            <button
              onClick={() => update({ sort: sort === 'league' ? 'time' : 'league' })}
              aria-label={`Sorted ${sort === 'league' ? 'by league' : 'by time'} — tap to switch`}
              className="flex h-11 shrink-0 items-center justify-between gap-2 rounded-xl border border-border bg-card px-3 text-[13px] font-semibold sm:min-w-[140px] sm:flex-1 sm:text-sm"
            >
              <span className="truncate"><span className="hidden sm:inline">By </span>{sort === 'league' ? 'League' : 'Time'}</span>
              <BsArrowDownUp size={14} className="shrink-0 text-muted-foreground" />
            </button>
          )}
          {tab !== 'live' && (
            <button
              onClick={() => update({ soon: !soon })}
              aria-pressed={soon}
              aria-label="Starting soon"
              title="Starting in the next 3 hours"
              className={`flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border transition-colors ${
                soon ? 'border-gold bg-gold/15' : 'border-border bg-card'
              }`}
            >
              <BsLightningChargeFill size={18} className="text-gold" />
            </button>
          )}
        </div>
      </div>

      {soon && tab !== 'live' && (
        <p className="px-1 text-xs font-semibold text-muted-foreground">
          <BsLightningChargeFill size={11} className="mr-1 inline text-gold" />Starting in the next 3 hours
        </p>
      )}

      {empty && (
        <div className="rounded-2xl border border-border bg-card p-12 text-center">
          <p className="mb-1 font-bold">No matches found</p>
          <p className="mb-4 text-sm text-muted-foreground">
            {tab === 'live' ? 'Nothing is in play right now.' : 'Try another sport or day.'}
          </p>
          {(filtersActive || tab !== 'upcoming') && (
            <button
              onClick={() => update({ sport: null, tab: 'upcoming', day: null, soon: false })}
              className="rounded-lg bg-secondary px-4 py-2 text-xs font-bold text-white"
            >
              Show all matches
            </button>
          )}
        </div>
      )}

      {awaitingOdds > 0 && !empty && tab === 'upcoming' && !filtersActive && (
        <p className="px-1 text-xs text-muted-foreground">
          {awaitingOdds} more upcoming match{awaitingOdds === 1 ? '' : 'es'} will appear once odds are published.
        </p>
      )}

      {tab === 'countries' ? (
        <div className="overflow-hidden rounded-2xl border border-border bg-card">
          {countries.map((c) => {
            const open = openCountries.has(c.name);
            return (
              <div key={c.name} className="border-b border-border last:border-b-0">
                <button
                  onClick={() => toggleCountry(c.name)}
                  aria-expanded={open}
                  className="flex w-full items-center gap-3 px-4 py-3.5 text-left transition-colors hover:bg-muted/40"
                >
                  {c.flag ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img src={c.flag} alt="" className="h-4 w-6 shrink-0 rounded-[3px] object-cover" />
                  ) : (
                    <GiTrophyCup size={17} className="shrink-0 text-muted-foreground" />
                  )}
                  <span className="min-w-0 flex-1 truncate text-sm font-bold">{c.name}</span>
                  <span className="text-xs font-semibold text-muted-foreground">
                    {c.leagues.length} league{c.leagues.length === 1 ? '' : 's'} · {c.events.length}
                  </span>
                  <BsChevronDown size={12} className={`shrink-0 text-muted-foreground transition-transform ${open ? '' : '-rotate-90'}`} />
                </button>
                {open && (
                  <div className="border-t border-border">
                    {leagueSections(c.leagues, `country:${c.name}`, `Other ${c.name} matches`)}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      ) : (
        groups.map((g) => {
          const meta = sportMeta(g.sport);
          return (
            <div key={g.sport ?? 'other'} className="overflow-hidden rounded-2xl border border-border bg-card">
              <MarketHeader title={meta.label} icon={meta.icon} count={g.events.length} />
              {sort === 'time'
                ? sortEvents(g.events).map((ev) => <EventRow key={ev.id} ev={ev} showLeague />)
                : leagueSections(g.leagues, g.sport ?? 'other', `Other ${meta.label.toLowerCase()}`)}
            </div>
          );
        })
      )}
    </section>
  );
}

