'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useMemo, useRef, useState } from 'react';
import { BsSearch, BsXLg, BsChevronRight } from 'react-icons/bs';
import { GiBasketballBall, GiAirplane, GiSoccerBall, GiTennisRacket, GiTrophy } from 'react-icons/gi';
import type { IconType } from 'react-icons';
import { LiveClock, TeamBadge } from '@/components/event-row';
import { config } from '@/lib/config';
import { useShell } from '@/lib/shell-context';
import { dayLabel, isLive, kickoffTime, teamNames, type EventItem } from '@/lib/sports';

const SHORTCUTS: { href: string; label: string; icon: IconType }[] = [
  { href: '/sportsbook?tab=live', label: 'Live betting', icon: GiTrophy },
  { href: '/aviator', label: 'Aviator', icon: GiAirplane },
  { href: '/sportsbook?sport=football', label: 'Football', icon: GiSoccerBall },
  { href: '/sportsbook?sport=basketball', label: 'Basketball', icon: GiBasketballBall },
  { href: '/sportsbook?sport=tennis', label: 'Tennis', icon: GiTennisRacket },
];

/** Every row of a list endpoint, following DRF `next` links (capped as a safety net). */
async function getList<T>(path: string, maxPages = 10): Promise<T[]> {
  const rows: T[] = [];
  let url: string | null = `${config.apiUrl}${path}`;
  try {
    for (let page = 0; url && page < maxPages; page++) {
      const res: Response = await fetch(url, { cache: 'no-store' });
      if (!res.ok) break;
      const json: T[] | { results?: T[]; next?: string | null } = await res.json();
      if (Array.isArray(json)) return json;
      rows.push(...((json.results ?? []) as T[]));
      url = json.next ?? null;
    }
  } catch {
    /* keep whatever loaded */
  }
  return rows;
}

/** Full-screen (mobile) / dropdown-panel (desktop) search across matches and teams. */
export function GlobalSearch() {
  const { searchOpen, setSearchOpen } = useShell();
  const pathname = usePathname();
  const [query, setQuery] = useState('');
  const [events, setEvents] = useState<EventItem[] | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Load the catalogues once, the first time search opens.
  useEffect(() => {
    if (!searchOpen || events) return;
    void getList<EventItem>('/events/?upcoming=true&priced=true&page_size=500').then((e) => setEvents(e));
  }, [searchOpen, events]);

  useEffect(() => {
    if (!searchOpen) return;
    inputRef.current?.focus();
    const prev = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    function onKey(e: KeyboardEvent) { if (e.key === 'Escape') setSearchOpen(false); }
    window.addEventListener('keydown', onKey);
    return () => { document.body.style.overflow = prev; window.removeEventListener('keydown', onKey); };
  }, [searchOpen, setSearchOpen]);

  useEffect(() => { setSearchOpen(false); }, [pathname, setSearchOpen]);

  const q = query.trim().toLowerCase();
  const eventHits = useMemo(
    () => (q.length < 2 ? [] : (events ?? []).filter((ev) =>
      [ev.name, ev.home_team?.name, ev.away_team?.name, ev.sport].some((s) => s?.toLowerCase().includes(q)),
    ).slice(0, 10)),
    [events, q],
  );

  if (!searchOpen) return null;

  const close = () => setSearchOpen(false);

  return (
    <div className="fixed inset-0 z-[70] bg-black/60 backdrop-blur-sm" onClick={close}>
      <div
        role="dialog"
        aria-label="Search"
        className="mx-auto flex h-full w-full max-w-2xl flex-col bg-background pt-[var(--safe-top)] sm:mt-20 sm:pt-0 sm:h-auto sm:max-h-[75vh] sm:rounded-2xl sm:border sm:border-border sm:shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center gap-2 border-b border-border p-3">
          <div className="relative flex-1">
            <BsSearch className="pointer-events-none absolute left-3.5 top-1/2 -translate-y-1/2 text-muted-foreground" size={15} />
            <input
              ref={inputRef}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search teams, matches, sports…"
              aria-label="Search"
              className="w-full rounded-xl border border-border bg-input py-3 pl-10 pr-3 text-[15px] outline-none focus:ring-2 focus:ring-ring"
            />
          </div>
          <button onClick={close} aria-label="Close search" className="flex h-11 w-11 items-center justify-center rounded-xl text-muted-foreground hover:bg-muted hover:text-foreground">
            <BsXLg size={16} />
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-3">
          {q.length < 2 ? (
            <>
              <p className="mb-2 px-1 text-[11px] font-extrabold uppercase tracking-wider text-muted-foreground">Quick links</p>
              <div className="flex flex-wrap gap-2">
                {SHORTCUTS.map((s) => {
                  const Icon = s.icon;
                  return (
                    <Link key={s.href} href={s.href} onClick={close} className="flex items-center gap-2 rounded-full border border-border bg-card px-3.5 py-2 text-sm font-bold hover:border-secondary">
                      <Icon size={15} className="text-secondary" /> {s.label}
                    </Link>
                  );
                })}
              </div>
              <p className="mt-6 px-1 text-xs text-muted-foreground">Type at least 2 characters to search.</p>
            </>
          ) : eventHits.length === 0 ? (
            <div className="py-12 text-center">
              <p className="font-bold">No results for “{query.trim()}”</p>
              <p className="mt-1 text-sm text-muted-foreground">Check the spelling or try a team or sport.</p>
            </div>
          ) : (
            <div className="space-y-5">
              {eventHits.length > 0 && (
                <section>
                  <p className="mb-2 px-1 text-[11px] font-extrabold uppercase tracking-wider text-muted-foreground">Matches</p>
                  <ul className="space-y-1">
                    {eventHits.map((ev) => {
                      const { home, away } = teamNames(ev);
                      return (
                        <li key={ev.id}>
                          <Link href={`/sportsbook/${ev.id}`} onClick={close} className="flex items-center gap-3 rounded-xl p-2 hover:bg-muted">
                            <TeamBadge team={ev.home_team} name={home} size={32} />
                            <span className="min-w-0 flex-1">
                              <span className="block truncate text-sm font-bold">{away ? `${home} v ${away}` : home}</span>
                              <span className="block text-xs text-muted-foreground" suppressHydrationWarning>
                                {isLive(ev) ? <LiveClock ev={ev} /> : ev.starts_at ? `${dayLabel(ev.starts_at)} · ${kickoffTime(ev.starts_at)}` : 'Time TBC'}
                              </span>
                            </span>
                            <BsChevronRight size={12} className="text-muted-foreground" />
                          </Link>
                        </li>
                      );
                    })}
                  </ul>
                </section>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
