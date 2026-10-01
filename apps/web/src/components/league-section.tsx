'use client';

import { BsChevronDown } from 'react-icons/bs';
import { GiTrophyCup } from 'react-icons/gi';
import { EventRow, LiveBadge } from '@/components/event-row';
import type { LeagueGroup } from '@/lib/sports';

/**
 * One league inside a sport block: a header (flag/logo · country · league ·
 * count) that collapses its matches, and the match rows beneath it.
 */
export function LeagueSection({ group, collapsed, onToggle, fallbackTitle }: {
  group: LeagueGroup;
  collapsed: boolean;
  onToggle: () => void;
  /** Title for matches with no league (e.g. "Other football"). */
  fallbackTitle: string;
}) {
  const { league } = group;
  const icon = league?.flag_url || league?.logo_url;
  return (
    <div className="border-b border-border last:border-b-0">
      <button
        onClick={onToggle}
        aria-expanded={!collapsed}
        className="flex w-full items-center gap-2.5 bg-muted/25 px-3 py-2 text-left transition-colors hover:bg-muted/50 sm:px-4"
      >
        {icon ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={icon} alt="" className="h-4 w-5 shrink-0 rounded-[3px] object-cover" />
        ) : (
          <GiTrophyCup size={15} className="shrink-0 text-muted-foreground" />
        )}
        <span className="min-w-0 flex-1 truncate text-[13px]">
          {league ? (
            <>
              {league.country && <span className="font-semibold text-muted-foreground">{league.country} · </span>}
              <span className="font-extrabold">{league.name}</span>
            </>
          ) : (
            <span className="font-extrabold">{fallbackTitle}</span>
          )}
        </span>
        {group.liveCount > 0 && <LiveBadge className="shrink-0" />}
        <span className="shrink-0 rounded-full bg-muted px-2 py-0.5 text-[11px] font-bold tabular-nums text-muted-foreground">
          {group.events.length}
        </span>
        <BsChevronDown
          size={12}
          className={`shrink-0 text-muted-foreground transition-transform ${collapsed ? '-rotate-90' : ''}`}
        />
      </button>
      {!collapsed && group.events.map((ev) => <EventRow key={ev.id} ev={ev} />)}
    </div>
  );
}
