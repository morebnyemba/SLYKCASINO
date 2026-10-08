'use client';

import { BsLockFill, BsTrophy } from 'react-icons/bs';
import { Badge, cx } from '@/components/console/ui';
import { teamNames, type AdminMatch, type LeagueRef, type TeamRef } from '@/lib/sportsbook';

export function TeamCrest({ team, name, size = 22 }: { team: TeamRef | null; name: string; size?: number }) {
  if (team?.logo_url) {
    // eslint-disable-next-line @next/next/no-img-element
    return <img src={team.logo_url} alt="" style={{ width: size, height: size }} className="shrink-0 rounded-full bg-white/5 object-contain" />;
  }
  return (
    <span
      style={{ width: size, height: size, fontSize: size * 0.42 }}
      className="flex shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-secondary/30 to-primary/30 font-extrabold text-foreground/80"
    >
      {name.charAt(0).toUpperCase() || '?'}
    </span>
  );
}

export function LeagueTag({ league, className }: { league: LeagueRef | null; className?: string }) {
  if (!league) return <span className={cx('text-xs text-muted-foreground', className)}>No league</span>;
  const icon = league.flag_url || league.logo_url;
  return (
    <span className={cx('flex min-w-0 items-center gap-1.5 text-xs text-muted-foreground', className)}>
      {icon ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={icon} alt="" className="h-3 w-4 shrink-0 rounded-[2px] object-cover" />
      ) : <BsTrophy size={11} className="shrink-0" />}
      <span className="truncate">{league.country ? `${league.country} · ` : ''}{league.name}</span>
    </span>
  );
}

export function MatchCell({ m }: { m: AdminMatch }) {
  const { home, away } = teamNames(m);
  const scored = m.score_home != null && m.score_away != null && m.state !== 'upcoming';
  return (
    <div className="min-w-[220px] space-y-1">
      <LeagueTag league={m.league_detail} />
      {[[m.home_team, home, m.score_home], [m.away_team, away, m.score_away]].map(([team, name, score], i) => (
        <div key={i} className="flex items-center gap-2">
          <TeamCrest team={team as TeamRef | null} name={name as string} size={20} />
          <span className="truncate text-[13.5px] font-semibold">{name as string}</span>
          {scored && <span className="ml-auto pl-2 font-mono text-[13px] font-extrabold tabular-nums">{score as number}</span>}
        </div>
      ))}
    </div>
  );
}

export function StateBadge({ m }: { m: AdminMatch }) {
  if (m.state === 'live') {
    const clock = m.status === 'HT' ? 'HT' : m.elapsed != null ? `${m.elapsed}'` : m.status;
    return <Badge tone="red" dot>Live {clock}</Badge>;
  }
  if (m.state === 'finished') return <Badge tone="slate">{m.status || 'FT'}</Badge>;
  if (m.state === 'void') return <Badge tone="slate">{m.status || 'Void'}</Badge>;
  if (m.state === 'started') return <Badge tone="gold">Kicked off</Badge>;
  if (!m.has_odds) return <Badge tone="gold">Awaiting odds</Badge>;
  if (!m.is_open) return <Badge tone="slate">Suspended</Badge>;
  return <Badge tone="green" dot>Open</Badge>;
}

export function OddsTrio({ m }: { m: AdminMatch }) {
  const cells = [['1', m.odds], ['X', m.odds_draw], ['2', m.odds_away]] as const;
  return (
    <div className="flex items-center gap-1">
      {cells.map(([label, v]) => (
        <span
          key={label}
          className={cx(
            'flex w-[58px] items-center justify-between rounded-lg px-2 py-1 font-mono text-xs',
            v ? 'bg-muted/70' : 'bg-muted/30 text-muted-foreground/50',
            !m.has_odds && 'opacity-50',
          )}
        >
          <span className="text-[10px] font-bold text-muted-foreground">{label}</span>
          <span className="font-bold">{v && m.has_odds ? Number(v).toFixed(2) : '—'}</span>
        </span>
      ))}
      {m.prices_locked && (
        <span title="Prices set by hand — the feed won't change them" className="ml-1 text-gold">
          <BsLockFill size={11} />
        </span>
      )}
    </div>
  );
}

export function SourceBadge({ m }: { m: AdminMatch }) {
  return m.source === 'feed'
    ? <Badge tone="indigo">Feed #{m.external_id}</Badge>
    : <Badge tone="gold">Manual</Badge>;
}
