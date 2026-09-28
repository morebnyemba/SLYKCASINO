'use client';

import Link from 'next/link';
import { BsChevronLeft } from 'react-icons/bs';
import { OddsButton } from '@/components/odds-button';
import { LiveBadge, TeamBadge, sportMeta } from '@/components/event-row';
import { useLiveOdds } from '@/lib/use-live-odds';
import { dayLabel, homeMove, isLive, kickoffTime, teamNames, type EventItem } from '@/lib/sports';

/**
 * Event page body: a scoreboard header and the match-result market, with prices
 * tracking the realtime `odds:<id>` channel. Picks go on the shared bet slip.
 */
export function EventMarkets({ ev }: { ev: EventItem }) {
  const live = useLiveOdds(ev.id, {
    odds: Number(ev.odds),
    odds_draw: ev.odds_draw != null ? Number(ev.odds_draw) : null,
    odds_away: ev.odds_away != null ? Number(ev.odds_away) : null,
  });
  const { home, away } = teamNames(ev);
  const sport = sportMeta(ev.sport);
  const SportIcon = sport.icon;
  const inPlay = isLive(ev);
  const closed = ev.is_open === false;
  const hasDraw = live.odds_draw != null;
  const hasAway = live.odds_away != null;

  const outcomes = [
    { selection: 'home' as const, label: away ? home : 'Win', odds: live.odds, move: live.live ? undefined : homeMove(ev) },
    ...(hasDraw ? [{ selection: 'draw' as const, label: 'Draw', odds: live.odds_draw, move: undefined }] : []),
    ...(hasAway ? [{ selection: 'away' as const, label: away ?? 'Away', odds: live.odds_away, move: undefined }] : []),
  ];

  return (
    <div className="space-y-4">
      <Link
        href={ev.sport ? `/sportsbook?sport=${ev.sport}` : '/sportsbook'}
        className="inline-flex items-center gap-1.5 text-xs font-bold text-muted-foreground hover:text-foreground"
      >
        <BsChevronLeft size={11} /> {sport.label}
      </Link>

      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-primary to-[#0f0a2b] p-5 text-white shadow-lg sm:p-7">
        <div className="mb-5 flex items-center gap-2 text-xs font-bold text-white/70">
          {SportIcon && <SportIcon size={14} />}
          <span>{sport.label}</span>
          <span className="ml-auto" suppressHydrationWarning>
            {inPlay ? <LiveBadge /> : ev.starts_at ? `${dayLabel(ev.starts_at)} · ${kickoffTime(ev.starts_at)}` : 'Time TBC'}
          </span>
        </div>
        <div className="flex items-center justify-between gap-4">
          <div className="flex min-w-0 flex-1 flex-col items-center gap-2 text-center">
            <TeamBadge team={ev.home_team} name={home} size={56} />
            <span className="w-full truncate text-base font-extrabold sm:text-lg">{home}</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            <span className="text-2xl font-black text-white/40">VS</span>
            {live.live && <span className="text-[10px] font-bold uppercase tracking-wide text-win">Live odds</span>}
          </div>
          <div className="flex min-w-0 flex-1 flex-col items-center gap-2 text-center">
            {away ? (
              <>
                <TeamBadge team={ev.away_team} name={away} size={56} />
                <span className="w-full truncate text-base font-extrabold sm:text-lg">{away}</span>
              </>
            ) : (
              <span className="text-sm text-white/60">Outright</span>
            )}
          </div>
        </div>
      </div>

      <div className="overflow-hidden rounded-2xl border border-border bg-card">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <h2 className="text-sm font-extrabold">{hasDraw ? 'Match result (1X2)' : 'Match winner'}</h2>
          {closed && <span className="rounded bg-muted px-2 py-0.5 text-[11px] font-bold text-muted-foreground">Suspended</span>}
        </div>
        <div className={`grid gap-2 p-3 ${outcomes.length === 3 ? 'grid-cols-3' : outcomes.length === 2 ? 'grid-cols-2' : 'grid-cols-1'}`}>
          {outcomes.map((o) => (
            <OddsButton
              key={o.selection}
              eventId={ev.id}
              eventName={ev.name}
              selection={o.selection}
              odds={o.odds}
              label={o.label}
              move={o.move}
              size="lg"
              disabled={closed}
            />
          ))}
        </div>
      </div>
    </div>
  );
}
