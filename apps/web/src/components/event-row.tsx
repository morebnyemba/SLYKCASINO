'use client';

import Link from 'next/link';
import { BsChevronRight } from 'react-icons/bs';
import type { IconType } from 'react-icons';
import { OddsButton } from '@/components/odds-button';
import { useLiveEvent } from '@/lib/live-board';
import { SPORT_CATEGORIES } from '@/components/sports-sidebar';
import {
  dayLabel, hasScore, homeMove, isLive, isMainOpen, isPriced, kickoffTime, marketShape, matchClock, teamNames, type EventItem, type Team,
} from '@/lib/sports';

export function sportMeta(id?: string): { label: string; icon?: IconType } {
  const cat = SPORT_CATEGORIES.find((c) => c.id === id);
  return cat ? { label: cat.label, icon: cat.icon } : { label: 'Other' };
}

export function TeamBadge({ team, name, size = 20 }: { team?: Team | null; name: string; size?: number }) {
  if (team?.logo_url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={team.logo_url} alt="" style={{ width: size, height: size }} className="shrink-0 rounded-full object-cover" />;
  }
  return (
    <span
      style={{ width: size, height: size, fontSize: size * 0.45 }}
      className="flex shrink-0 items-center justify-center rounded-full bg-muted font-extrabold text-muted-foreground"
    >
      {name.charAt(0).toUpperCase()}
    </span>
  );
}

export function LiveBadge({ className = '' }: { className?: string }) {
  return (
    <span className={`inline-flex items-center gap-1 rounded bg-live px-1.5 py-0.5 text-[10px] font-extrabold tracking-wide text-live-foreground ${className}`}>
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-white" /> LIVE
    </span>
  );
}

/** Quiet in-play marker for lists: a small pulsing dot and the match minute
 * ("● 61'", or "● HT"/"● Live"). The bold LIVE badge is kept for the match page. */
export function LiveClock({ ev, className = '' }: { ev: EventItem; className?: string }) {
  const clock = matchClock(ev);
  return (
    <span className={`inline-flex items-center gap-1.5 text-[11.5px] font-extrabold tabular-nums text-live ${className}`}>
      <span className="h-1.5 w-1.5 shrink-0 animate-pulse rounded-full bg-live" aria-hidden />
      {clock || 'Live'}
    </span>
  );
}

/** Kickoff/live status, stacked for the time column. */
function EventStatus({ ev, inline = false }: { ev: EventItem; inline?: boolean }) {
  const clock = matchClock(ev);
  if (isLive(ev)) return <LiveClock ev={ev} />;
  if (clock) return <span className="text-[11px] font-extrabold text-muted-foreground">{clock}</span>;
  if (!ev.starts_at) return <span className="text-[11px] font-semibold text-muted-foreground">TBC</span>;
  return inline ? (
    // Kickoff times render in the viewer's timezone, which can differ from the server's.
    <span suppressHydrationWarning className="text-[11px] font-semibold text-muted-foreground">
      {dayLabel(ev.starts_at)} · {kickoffTime(ev.starts_at)}
    </span>
  ) : (
    <span className="flex flex-col leading-tight">
      <span suppressHydrationWarning className="text-[13px] font-extrabold tabular-nums">{kickoffTime(ev.starts_at)}</span>
      <span suppressHydrationWarning className="text-[10.5px] font-semibold text-muted-foreground">{dayLabel(ev.starts_at)}</span>
    </span>
  );
}

const ODDS_COLS = 'grid grid-cols-3 gap-1.5 w-[178px] sm:w-[222px]';

/** Section header for a block of events, with the 1 / X / 2 column captions. */
export function MarketHeader({ title, icon: Icon, count }: { title: string; icon?: IconType; count?: number }) {
  return (
    <div className="flex items-center gap-2 border-b border-border bg-muted/40 px-3 py-2.5 sm:px-4">
      {Icon && <Icon size={16} className="text-secondary" />}
      <span className="text-sm font-extrabold">{title}</span>
      {count != null && <span className="text-xs font-semibold text-muted-foreground">{count}</span>}
      <div className={`ml-auto ${ODDS_COLS} sm:mr-[52px]`}>
        {['1', 'X', '2'].map((l) => (
          <span key={l} className="text-center text-[11px] font-extrabold text-muted-foreground">{l}</span>
        ))}
      </div>
    </div>
  );
}

/** One compact market row: status, teams, and 1/X/2 price buttons — kept live
 * (prices, score, clock, locks) from the shared board channel. */
export function EventRow({ ev: snapshot, showLeague = false }: {
  ev: EventItem;
  /** Name the competition on the row (lists sorted by time, not grouped by league). */
  showLeague?: boolean;
}) {
  const { ev, moves } = useLiveEvent(snapshot);
  const { home, away } = teamNames(ev);
  const shape = marketShape(ev);
  const priced = isPriced(ev);
  // Pre-match betting closes at kick-off; in play the prices stay locked unless
  // the match is trading live.
  const closed = !isMainOpen(ev);
  const href = `/sportsbook/${ev.id}`;

  return (
    <div className="flex items-center gap-3 border-b border-border px-3 py-2.5 transition-colors last:border-b-0 hover:bg-muted/30 sm:px-4">
      <div className="hidden w-16 shrink-0 md:block">
        <EventStatus ev={ev} />
      </div>
      <Link href={href} className="min-w-0 flex-1">
        <div className="mb-1 flex items-center gap-2 md:hidden">
          <EventStatus ev={ev} inline />
          {!!ev.markets_count && (
            <span className="ml-auto rounded bg-muted px-1.5 py-0.5 text-[10px] font-extrabold text-muted-foreground sm:hidden">
              +{ev.markets_count} markets
            </span>
          )}
        </div>
        {showLeague && ev.league && (
          <p className="mb-1 flex min-w-0 items-center gap-1.5 text-[11px] font-semibold text-muted-foreground">
            {(ev.league.flag_url || ev.league.logo_url) && (
              // eslint-disable-next-line @next/next/no-img-element
              <img src={ev.league.flag_url || ev.league.logo_url} alt="" className="h-3 w-4 shrink-0 rounded-[2px] object-cover" />
            )}
            <span className="truncate">{ev.league.country ? `${ev.league.country} · ` : ''}{ev.league.name}</span>
          </p>
        )}
        <div className="space-y-1">
          <div className="flex items-center gap-2">
            <TeamBadge team={ev.home_team} name={home} size={18} />
            <span className="min-w-0 flex-1 truncate text-[13.5px] font-semibold">{home}</span>
            {hasScore(ev) && <span className="pr-1 text-[13.5px] font-extrabold tabular-nums text-live">{ev.score_home}</span>}
          </div>
          {away && (
            <div className="flex items-center gap-2">
              <TeamBadge team={ev.away_team} name={away} size={18} />
              <span className="min-w-0 flex-1 truncate text-[13.5px] font-semibold">{away}</span>
              {hasScore(ev) && <span className="pr-1 text-[13.5px] font-extrabold tabular-nums text-live">{ev.score_away}</span>}
            </div>
          )}
        </div>
      </Link>
      <div className={ODDS_COLS}>
        <OddsButton eventId={ev.id} eventName={ev.name} selection="home" odds={priced ? ev.odds : null} move={moves.home ?? homeMove(ev)} disabled={closed} />
        <OddsButton eventId={ev.id} eventName={ev.name} selection="draw" odds={priced && shape === '1x2' ? ev.odds_draw : null} move={moves.draw} disabled={closed} />
        <OddsButton eventId={ev.id} eventName={ev.name} selection="away" odds={priced && shape !== 'single' ? ev.odds_away : null} move={moves.away} disabled={closed} />
      </div>
      <Link
        href={href}
        aria-label={`All markets for ${ev.name}`}
        title="All markets"
        className="hidden h-11 w-10 shrink-0 items-center justify-center rounded-lg text-[11px] font-extrabold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground sm:flex"
      >
        {ev.markets_count ? `+${ev.markets_count}` : <BsChevronRight size={13} />}
      </Link>
    </div>
  );
}

/** Card for the "Top matches" strip — teams stacked with the full 1X2 underneath. */
export function FeaturedMatchCard({ ev: snapshot }: { ev: EventItem }) {
  const { ev, moves } = useLiveEvent(snapshot);
  const { home, away } = teamNames(ev);
  const shape = marketShape(ev);
  const priced = isPriced(ev);
  const closed = !isMainOpen(ev);
  const sport = sportMeta(ev.sport);
  const SportIcon = sport.icon;

  return (
    <div className="flex h-full w-[280px] flex-col rounded-2xl border border-border bg-card p-3.5 transition-colors hover:border-secondary/50 sm:w-[300px]">
      <div className="mb-3 flex items-center gap-2 text-[11px] font-bold text-muted-foreground">
        {SportIcon && <SportIcon size={13} />}
        <span>{sport.label}</span>
        <span suppressHydrationWarning className="ml-auto">
          {isLive(ev) ? <LiveClock ev={ev} /> : ev.starts_at ? `${dayLabel(ev.starts_at)} · ${kickoffTime(ev.starts_at)}` : 'TBC'}
        </span>
      </div>
      <Link href={`/sportsbook/${ev.id}`} className="mb-3 flex items-center justify-between gap-2">
        <div className="flex min-w-0 flex-1 flex-col items-center gap-1.5 text-center">
          <TeamBadge team={ev.home_team} name={home} size={36} />
          <span className="w-full truncate text-[13px] font-bold">{home}</span>
        </div>
        <span className="text-xs font-extrabold text-muted-foreground">VS</span>
        <div className="flex min-w-0 flex-1 flex-col items-center gap-1.5 text-center">
          {away ? (
            <>
              <TeamBadge team={ev.away_team} name={away} size={36} />
              <span className="w-full truncate text-[13px] font-bold">{away}</span>
            </>
          ) : (
            <span className="text-xs text-muted-foreground">—</span>
          )}
        </div>
      </Link>
      <div className="mt-auto grid grid-cols-3 gap-1.5">
        <OddsButton eventId={ev.id} eventName={ev.name} selection="home" odds={priced ? ev.odds : null} label="1" move={moves.home ?? homeMove(ev)} disabled={closed} />
        <OddsButton eventId={ev.id} eventName={ev.name} selection="draw" odds={priced && shape === '1x2' ? ev.odds_draw : null} label="X" move={moves.draw} disabled={closed} />
        <OddsButton eventId={ev.id} eventName={ev.name} selection="away" odds={priced && shape !== 'single' ? ev.odds_away : null} label="2" move={moves.away} disabled={closed} />
      </div>
      {!!ev.markets_count && (
        <Link
          href={`/sportsbook/${ev.id}`}
          className="mt-2 flex items-center justify-center gap-1 rounded-lg py-1.5 text-[11.5px] font-bold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          +{ev.markets_count} more markets <BsChevronRight size={10} />
        </Link>
      )}
    </div>
  );
}
