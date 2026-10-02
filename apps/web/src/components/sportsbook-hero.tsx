'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { BsChevronRight } from 'react-icons/bs';
import { FaChevronLeft, FaChevronRight } from 'react-icons/fa';
import { GiTrophyCup } from 'react-icons/gi';
import { PromoSlide, type Banner } from '@/components/banner-slider';
import { LiveClock, TeamBadge } from '@/components/event-row';
import { OddsButton } from '@/components/odds-button';
import { useLiveEvent } from '@/lib/live-board';
import {
  dayLabel, hasScore, isLive, isMainOpen, isPriced, kickoffTime, marketShape, teamNames, type EventItem,
} from '@/lib/sports';

const AUTO_ADVANCE_MS = 7000;

type Slide = { kind: 'promo'; key: string; banner: Banner } | { kind: 'match'; key: string; event: EventItem };

/** A match banner built from feed data: league, crests, kick-off or live score,
 * and live 1X2 prices that go straight onto the bet slip. */
function MatchSlide({ event: snapshot }: { event: EventItem }) {
  const { ev, moves } = useLiveEvent(snapshot);
  const { home, away } = teamNames(ev);
  const league = ev.league;
  const shape = marketShape(ev);
  const priced = isPriced(ev);
  const closed = !isMainOpen(ev);
  const live = isLive(ev);
  const href = `/sportsbook/${ev.id}`;

  return (
    <div className="absolute inset-0 overflow-hidden bg-gradient-to-br from-primary via-[#1b1446] to-[#0b0820]">
      {/* Decorative glow + faded league mark */}
      <div className="pointer-events-none absolute -right-16 -top-24 h-72 w-72 rounded-full bg-secondary/30 blur-3xl" />
      <div className="pointer-events-none absolute -bottom-28 -left-10 h-64 w-64 rounded-full bg-win/10 blur-3xl" />
      {league?.logo_url && (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={league.logo_url} alt="" aria-hidden className="pointer-events-none absolute -right-6 top-1/2 h-56 w-56 -translate-y-1/2 object-contain opacity-[0.07]" />
      )}

      <div className="relative flex h-full flex-col justify-between gap-2 p-4 pb-7 text-white sm:p-6 sm:pb-8">
        <div className="flex items-center gap-2 text-[11px] font-bold sm:text-xs">
          <span className="flex min-w-0 items-center gap-1.5 rounded-md bg-white/10 px-2 py-1 backdrop-blur-sm">
            {league?.flag_url || league?.logo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={league.flag_url || league.logo_url} alt="" className="h-3.5 w-[18px] shrink-0 rounded-[2px] object-cover" />
            ) : (
              <GiTrophyCup size={12} className="shrink-0 text-gold" />
            )}
            <span className="truncate">{league ? `${league.country ? `${league.country} · ` : ''}${league.name}` : 'Featured match'}</span>
          </span>
          <span className="ml-auto shrink-0" suppressHydrationWarning>
            {live ? <LiveClock ev={ev} className="text-white" /> : ev.starts_at ? `${dayLabel(ev.starts_at)} · ${kickoffTime(ev.starts_at)}` : ''}
          </span>
        </div>

        <Link href={href} className="flex items-center justify-center gap-3 sm:gap-6">
          <div className="flex min-w-0 flex-1 flex-col items-center gap-1.5 text-center">
            <TeamBadge team={ev.home_team} name={home} size={44} />
            <span className="w-full truncate text-sm font-extrabold sm:text-lg">{home}</span>
          </div>
          <div className="shrink-0 text-center">
            {hasScore(ev) && live ? (
              <span className="text-3xl font-black tabular-nums sm:text-4xl">{ev.score_home} – {ev.score_away}</span>
            ) : (
              <span className="text-lg font-black text-white/50 sm:text-2xl">VS</span>
            )}
          </div>
          <div className="flex min-w-0 flex-1 flex-col items-center gap-1.5 text-center">
            <TeamBadge team={ev.away_team} name={away ?? ''} size={44} />
            <span className="w-full truncate text-sm font-extrabold sm:text-lg">{away}</span>
          </div>
        </Link>

        <div className="flex items-center gap-2">
          <div className="grid flex-1 grid-cols-3 gap-1.5 sm:gap-2">
            <OddsButton eventId={ev.id} eventName={ev.name} selection="home" label="1" odds={priced ? ev.odds : null} move={moves.home} disabled={closed} />
            <OddsButton eventId={ev.id} eventName={ev.name} selection="draw" label="X" odds={priced && shape === '1x2' ? ev.odds_draw : null} move={moves.draw} disabled={closed} />
            <OddsButton eventId={ev.id} eventName={ev.name} selection="away" label="2" odds={priced && shape !== 'single' ? ev.odds_away : null} move={moves.away} disabled={closed} />
          </div>
          <Link
            href={href}
            className="hidden h-11 shrink-0 items-center gap-1 rounded-lg bg-white/10 px-3 text-xs font-bold backdrop-blur-sm transition-colors hover:bg-white/20 sm:flex"
          >
            {ev.markets_count ? `+${ev.markets_count} markets` : 'All markets'} <BsChevronRight size={11} />
          </Link>
        </div>
      </div>
    </div>
  );
}

/**
 * Sportsbook hero: the operator's sportsbook promos first, then match banners
 * for the day's biggest fixtures. Auto-advances, pausing while the pointer is
 * over it so a price can be tapped.
 */
export function SportsbookHero({ banners, matches }: { banners: Banner[]; matches: EventItem[] }) {
  const slides: Slide[] = [
    ...banners.map((b) => ({ kind: 'promo' as const, key: `b${b.id}`, banner: b })),
    ...matches.map((ev) => ({ kind: 'match' as const, key: `m${ev.id}`, event: ev })),
  ];
  const count = slides.length;
  const [index, setIndex] = useState(0);
  const [paused, setPaused] = useState(false);

  const go = useCallback((next: number) => {
    setIndex(() => (count === 0 ? 0 : (next + count) % count));
  }, [count]);

  useEffect(() => {
    if (count <= 1 || paused) return;
    const t = setInterval(() => setIndex((p) => (p + 1) % count), AUTO_ADVANCE_MS);
    return () => clearInterval(t);
  }, [count, paused]);

  useEffect(() => { if (index >= count) setIndex(0); }, [index, count]);

  if (count === 0) return null;

  return (
    <div
      className="group relative h-56 overflow-hidden rounded-2xl sm:h-60 md:h-64"
      onMouseEnter={() => setPaused(true)}
      onMouseLeave={() => setPaused(false)}
      onFocusCapture={() => setPaused(true)}
      onBlurCapture={() => setPaused(false)}
    >
      {slides.map((s, i) => (
        <div
          key={s.key}
          className={`absolute inset-0 transition-opacity duration-700 ${i === index ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
          aria-hidden={i === index ? undefined : true}
        >
          {s.kind === 'promo' ? <PromoSlide b={s.banner} /> : <MatchSlide event={s.event} />}
        </div>
      ))}

      {count > 1 && (
        <>
          <button
            type="button"
            aria-label="Previous banner"
            onClick={() => go(index - 1)}
            className="absolute left-2 top-1/2 z-10 hidden h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/40 text-white opacity-0 backdrop-blur transition-opacity hover:bg-black/60 group-hover:opacity-100 sm:flex"
          >
            <FaChevronLeft size={13} />
          </button>
          <button
            type="button"
            aria-label="Next banner"
            onClick={() => go(index + 1)}
            className="absolute right-2 top-1/2 z-10 hidden h-9 w-9 -translate-y-1/2 items-center justify-center rounded-full bg-black/40 text-white opacity-0 backdrop-blur transition-opacity hover:bg-black/60 group-hover:opacity-100 sm:flex"
          >
            <FaChevronRight size={13} />
          </button>
          <div className="absolute bottom-2.5 left-1/2 z-10 flex -translate-x-1/2 gap-1.5">
            {slides.map((s, i) => (
              <button
                key={s.key}
                type="button"
                aria-label={`Show banner ${i + 1}`}
                onClick={() => go(i)}
                className={`h-1.5 rounded-full transition-all ${i === index ? 'w-5 bg-white' : 'w-1.5 bg-white/40 hover:bg-white/70'}`}
              />
            ))}
          </div>
        </>
      )}
    </div>
  );
}
