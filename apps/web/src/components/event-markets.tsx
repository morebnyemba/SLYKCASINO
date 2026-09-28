'use client';

import Link from 'next/link';
import { Fragment, useMemo, useState } from 'react';
import { BsChevronLeft, BsChevronDown, BsCheckCircleFill, BsLockFill } from 'react-icons/bs';
import { OddsButton } from '@/components/odds-button';
import { LiveBadge, TeamBadge, sportMeta } from '@/components/event-row';
import { useLiveOdds } from '@/lib/use-live-odds';
import { useLiveMarkets } from '@/lib/use-live-markets';
import { formatOdds, useSettings } from '@/lib/settings-context';
import {
  MARKET_GROUPS, dayLabel, hasScore, homeMove, isFinished, isLive, kickoffTime, matchClock,
  teamNames, withTeamNames, type EventItem, type Market, type MarketGroup, type MarketOutcome,
} from '@/lib/sports';

type Tab = 'all' | MarketGroup;

/** A card on the board: one market, or several lines of the same market as a table. */
type Block =
  | { type: 'single'; id: string; group: MarketGroup; market: Market }
  | { type: 'lines'; id: string; group: MarketGroup; name: string; markets: Market[] };

/** Line-based markets ("Total goals 2.5", "Asian handicap -1") collapse into one table. */
function buildBlocks(markets: Market[]): Block[] {
  const blocks: Block[] = [];
  const lined = new Map<string, Block & { type: 'lines' }>();
  for (const m of markets) {
    if (m.line == null || m.kind === 'manual') {
      blocks.push({ type: 'single', id: `m${m.id}`, group: m.group, market: m });
      continue;
    }
    const key = `${m.kind}:${m.metric ?? 'goals'}:${m.period}`;
    let block = lined.get(key);
    if (!block) {
      block = { type: 'lines', id: key, group: m.group, name: m.name.replace(/\s[+-]?\d+(\.\d+)?$/, ''), markets: [] };
      lined.set(key, block);
      blocks.push(block);
    }
    block.markets.push(m);
  }
  return blocks;
}

function fmtLine(line: string | null | undefined, signed: boolean) {
  const n = Number(line);
  if (!Number.isFinite(n)) return '';
  const text = String(n);
  return signed && n > 0 ? `+${text}` : text;
}

function Collapsible({ title, badge, children, defaultOpen = true }: {
  title: string; badge?: React.ReactNode; children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <section className="overflow-hidden rounded-2xl border border-border bg-card">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-center gap-2 px-4 py-3 text-left transition-colors hover:bg-muted/30"
      >
        <h3 className="flex-1 text-sm font-extrabold">{title}</h3>
        {badge}
        <BsChevronDown size={12} className={`text-muted-foreground transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && <div className="border-t border-border p-3">{children}</div>}
    </section>
  );
}

/** Static chip for settled outcomes: winners ticked, the rest dimmed. */
function SettledOutcome({ outcome, label, stack = false }: {
  outcome: Pick<MarketOutcome, 'odds' | 'result'>; label: string; stack?: boolean;
}) {
  const { oddsFormat } = useSettings();
  const won = outcome.result === 'won';
  return (
    <span className={`flex min-h-11 rounded-lg px-3 py-2 text-[13.5px] font-bold ${
      stack ? 'flex-col items-center justify-center gap-0.5 sm:flex-row sm:justify-between sm:gap-2' : 'items-center justify-between gap-2'
    } ${
      won ? 'bg-win/15 text-foreground ring-1 ring-win' : outcome.result === 'void' ? 'bg-muted/50 text-muted-foreground' : 'bg-odds/40 text-muted-foreground/70'
    }`}>
      {label && (
        <span className={`flex min-w-0 max-w-full items-center gap-1.5 text-[11.5px] ${stack ? 'justify-center' : ''}`}>
          {won && <BsCheckCircleFill size={11} className="shrink-0 text-win" />}
          <span className="truncate">{label}</span>
        </span>
      )}
      <span className="flex items-center gap-1.5 tabular-nums">
        {!label && won && <BsCheckCircleFill size={11} className="text-win" />}
        {outcome.result === 'void' ? 'Void' : formatOdds(Number(outcome.odds), oddsFormat)}
      </span>
    </span>
  );
}

function StatusBadge({ market }: { market: Market }) {
  if (market.settled) return <span className="rounded bg-muted px-2 py-0.5 text-[10.5px] font-bold text-muted-foreground">Settled</span>;
  if (!market.is_open) return (
    <span className="flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-[10.5px] font-bold text-muted-foreground">
      <BsLockFill size={9} /> Suspended
    </span>
  );
  return null;
}

export function EventMarkets({ ev }: { ev: EventItem }) {
  const live = useLiveOdds(ev.id, {
    odds: Number(ev.odds),
    odds_draw: ev.odds_draw != null ? Number(ev.odds_draw) : null,
    odds_away: ev.odds_away != null ? Number(ev.odds_away) : null,
  });
  const initialMarkets = useMemo(() => ev.markets ?? [], [ev.markets]);
  const markets = useLiveMarkets(ev.id, initialMarkets);
  const [tab, setTab] = useState<Tab>('all');

  const { home, away } = teamNames(ev);
  const sport = sportMeta(ev.sport);
  const SportIcon = sport.icon;
  const inPlay = isLive(ev);
  const finished = isFinished(ev);
  const closed = ev.is_open === false;
  const clock = matchClock(ev);
  const names = (text: string) => withTeamNames(text, home, away);
  const facts = ev.match_facts;

  const hasDraw = live.odds_draw != null;
  const hasAway = live.odds_away != null;
  const resultOutcomes = [
    { selection: 'home' as const, label: away ? home : 'Win', odds: live.odds, move: live.live ? undefined : homeMove(ev) },
    ...(hasDraw ? [{ selection: 'draw' as const, label: 'Draw', odds: live.odds_draw, move: undefined }] : []),
    ...(hasAway ? [{ selection: 'away' as const, label: away ?? 'Away', odds: live.odds_away, move: undefined }] : []),
  ];

  // Once a match has finished with a score, show the 1X2 outcome instead of dead prices.
  const finalResult = finished && hasScore(ev)
    ? (ev.score_home! > ev.score_away! ? 'home' : ev.score_home! < ev.score_away! ? 'away' : 'draw')
    : null;

  const blocks = useMemo(() => buildBlocks(markets), [markets]);
  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    for (const m of markets) c[m.group] = (c[m.group] ?? 0) + 1;
    return c;
  }, [markets]);
  const tabs: { id: Tab; label: string; count: number }[] = [
    { id: 'all', label: 'All', count: markets.length + 1 },
    ...MARKET_GROUPS.filter((g) => counts[g.id]).map((g) => ({
      id: g.id, label: g.label, count: (counts[g.id] ?? 0) + (g.id === 'main' ? 1 : 0),
    })),
  ];
  const visible = tab === 'all' ? blocks : blocks.filter((b) => b.group === tab);
  const showResult = tab === 'all' || tab === 'main';

  const outcomeProps = (m: Market, o: MarketOutcome) => ({
    eventId: ev.id,
    eventName: ev.name,
    odds: o.odds,
    disabled: closed || !m.is_open || !o.is_open,
    move: o.previous_odds != null && Number(o.previous_odds) !== Number(o.odds)
      ? (Number(o.odds) > Number(o.previous_odds) ? 'up' as const : 'down' as const)
      : undefined,
    outcome: { id: o.id, marketId: m.id, marketName: names(m.name), label: names(o.label) },
  });

  function renderSingle(m: Market) {
    if (m.group === 'scorers') return renderScorers(m);
    const many = m.outcomes.length > 3;
    const cols = m.outcomes.length === 2 ? 'grid-cols-2' : many ? 'grid-cols-2 sm:grid-cols-3' : 'grid-cols-3';
    return (
      <Collapsible key={m.id} title={names(m.name)} badge={<StatusBadge market={m} />}>
        <div className={`grid gap-2 ${cols}`}>
          {m.outcomes.map((o) => m.settled
            ? <SettledOutcome key={o.id} outcome={o} label={names(o.label)} stack={m.outcomes.length === 3} />
            : <OddsButton key={o.id} {...outcomeProps(m, o)} label={names(o.label)} size="sm" stackOnMobile={m.outcomes.length === 3} />)}
        </div>
      </Collapsible>
    );
  }

  /** Goalscorer markets can list dozens of players: two columns of name + price. */
  function renderScorers(m: Market) {
    return (
      <Collapsible key={m.id} title={m.name} badge={<StatusBadge market={m} />}>
        <div className="grid gap-2 sm:grid-cols-2">
          {m.outcomes.map((o) => m.settled
            ? <SettledOutcome key={o.id} outcome={o} label={o.label} />
            : <OddsButton key={o.id} {...outcomeProps(m, o)} label={o.label} size="sm" />)}
        </div>
      </Collapsible>
    );
  }

  function renderLines(block: Block & { type: 'lines' }) {
    // Column order comes from the first line (Over/Under, Home/Away, Home/Draw/Away).
    const columns = block.markets[0].outcomes.map((o) => o.key);
    const colLabel = (key: string) => names(({ over: 'Over', under: 'Under', home: 'Home', draw: 'Draw', away: 'Away' } as Record<string, string>)[key] ?? key);
    const signed = block.markets[0].kind.includes('handicap');
    const grid = columns.length === 3 ? 'grid-cols-[56px_repeat(3,minmax(0,1fr))]' : 'grid-cols-[56px_repeat(2,minmax(0,1fr))]';
    const anyOpen = block.markets.some((m) => m.is_open && !m.settled);
    return (
      <Collapsible
        key={block.id}
        title={names(block.name)}
        badge={!anyOpen ? <StatusBadge market={block.markets[0]} /> : undefined}
      >
        <div className={`mb-1.5 grid gap-2 px-0.5 text-center text-[11px] font-extrabold text-muted-foreground ${grid}`}>
          <span className="text-left">{signed ? 'Line' : ({ corners: 'Corners', cards: 'Cards' } as Record<string, string>)[block.markets[0].metric ?? ''] ?? 'Goals'}</span>
          {columns.map((c) => <span key={c} className="truncate">{colLabel(c)}</span>)}
        </div>
        <div className="space-y-1.5">
          {block.markets.map((m) => (
            <div key={m.id} className={`grid items-center gap-2 ${grid}`}>
              <span className="text-sm font-extrabold tabular-nums">{fmtLine(m.line, signed)}</span>
              {columns.map((c) => {
                const o = m.outcomes.find((x) => x.key === c);
                if (!o) return <span key={c} className="flex h-11 items-center justify-center rounded-lg bg-odds/40 text-muted-foreground/50">—</span>;
                return m.settled
                  ? <SettledOutcome key={c} outcome={o} label="" />
                  : <OddsButton key={c} {...outcomeProps(m, o)} />;
              })}
            </div>
          ))}
        </div>
      </Collapsible>
    );
  }

  return (
    <div className="space-y-4">
      <Link
        href={ev.sport ? `/sportsbook?sport=${ev.sport}` : '/sportsbook'}
        className="inline-flex items-center gap-1.5 text-xs font-bold text-muted-foreground hover:text-foreground"
      >
        <BsChevronLeft size={11} /> {sport.label}
      </Link>

      {/* Scoreboard */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-primary to-[#0f0a2b] p-5 text-white shadow-lg sm:p-7">
        <div className="mb-5 flex items-center gap-2 text-xs font-bold text-white/70">
          {SportIcon && <SportIcon size={14} />}
          <span>{sport.label}</span>
          <span className="ml-auto flex items-center gap-2" suppressHydrationWarning>
            {inPlay && <LiveBadge />}
            {clock ? <span className="tabular-nums text-white">{clock}</span>
              : !inPlay && (ev.starts_at ? `${dayLabel(ev.starts_at)} · ${kickoffTime(ev.starts_at)}` : 'Time TBC')}
          </span>
        </div>
        <div className="flex items-center justify-between gap-4">
          <div className="flex min-w-0 flex-1 flex-col items-center gap-2 text-center">
            <TeamBadge team={ev.home_team} name={home} size={56} />
            <span className="w-full truncate text-base font-extrabold sm:text-lg">{home}</span>
          </div>
          <div className="flex flex-col items-center gap-1">
            {hasScore(ev) ? (
              <>
                <span className="text-4xl font-black tabular-nums tracking-tight">{ev.score_home} – {ev.score_away}</span>
                {ev.ht_score_home != null && ev.ht_score_away != null && (
                  <span className="text-[11px] font-bold text-white/60">HT {ev.ht_score_home}–{ev.ht_score_away}</span>
                )}
              </>
            ) : (
              <span className="text-2xl font-black text-white/40">VS</span>
            )}
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

      {facts && (facts.corners || facts.yellow || facts.goals?.length) ? (
        <div className="grid gap-3 rounded-2xl border border-border bg-card p-4 text-sm sm:grid-cols-2">
          {facts.goals && facts.goals.length > 0 && (
            <ul className="space-y-1">
              {facts.goals.map((g, i) => (
                <li key={i} className={`flex items-center gap-2 ${g.side === 'away' ? 'sm:justify-start' : ''}`}>
                  <span className="w-10 shrink-0 text-xs font-bold tabular-nums text-muted-foreground">
                    {g.minute}{g.extra ? `+${g.extra}` : ''}'
                  </span>
                  <span className="font-semibold">{g.player}</span>
                  <span className="text-xs text-muted-foreground">
                    {g.own_goal ? '(OG)' : g.penalty ? '(pen)' : ''} · {g.side === 'home' ? home : away}
                  </span>
                </li>
              ))}
            </ul>
          )}
          <dl className="grid grid-cols-[1fr_auto_1fr] items-center gap-x-3 gap-y-1 text-center">
            {([['Corners', facts.corners], ['Yellow cards', facts.yellow], ['Red cards', facts.red]] as const)
              .filter(([, v]) => v)
              .map(([label, v]) => (
                <Fragment key={label}>
                  <dd className="font-extrabold tabular-nums">{v![0]}</dd>
                  <dt className="text-xs font-semibold text-muted-foreground">{label}</dt>
                  <dd className="font-extrabold tabular-nums">{v![1]}</dd>
                </Fragment>
              ))}
          </dl>
        </div>
      ) : null}

      {(closed || finished) && (
        <p className="rounded-xl border border-border bg-card px-4 py-3 text-sm font-semibold text-muted-foreground">
          {finished ? 'This match has finished — markets are settled or awaiting settlement.' : 'Betting is closed on this match.'}
        </p>
      )}

      {/* Market group tabs */}
      {markets.length > 0 && (
        <div className="sticky top-[var(--header-h)] z-20 -mx-3 bg-background/95 px-3 py-2 backdrop-blur sm:mx-0 sm:px-0">
          <div className="no-scrollbar flex gap-1 overflow-x-auto rounded-2xl border border-border bg-card p-1">
            {tabs.map((t) => (
              <button
                key={t.id}
                onClick={() => setTab(t.id)}
                className={`flex shrink-0 items-center gap-1.5 rounded-xl px-3.5 py-2 text-[13px] font-bold transition-colors ${
                  tab === t.id ? 'bg-secondary text-white shadow' : 'text-muted-foreground hover:bg-muted hover:text-foreground'
                }`}
              >
                {t.label}
                <span className={`rounded-full px-1.5 text-[10px] ${tab === t.id ? 'bg-white/20' : 'bg-muted'}`}>{t.count}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="space-y-3">
        {showResult && (
          <Collapsible title={hasDraw ? 'Match result (1X2)' : 'Match winner'} badge={finalResult ? (
            <span className="rounded bg-muted px-2 py-0.5 text-[10.5px] font-bold text-muted-foreground">Settled</span>
          ) : closed ? (
            <span className="flex items-center gap-1 rounded bg-muted px-2 py-0.5 text-[10.5px] font-bold text-muted-foreground"><BsLockFill size={9} /> Closed</span>
          ) : undefined}>
            <div className={`grid gap-2 ${resultOutcomes.length === 3 ? 'grid-cols-3' : resultOutcomes.length === 2 ? 'grid-cols-2' : 'grid-cols-1'}`}>
              {finalResult ? resultOutcomes.map((o) => (
                <SettledOutcome
                  key={o.selection}
                  label={o.label}
                  stack={resultOutcomes.length === 3}
                  outcome={{ odds: o.odds ?? 0, result: o.selection === finalResult ? 'won' : 'lost' }}
                />
              )) : resultOutcomes.map((o) => (
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
                  stackOnMobile={resultOutcomes.length === 3}
                />
              ))}
            </div>
          </Collapsible>
        )}
        {visible.map((b) => (b.type === 'single' ? renderSingle(b.market) : renderLines(b)))}
        {markets.length === 0 && (
          <p className="rounded-2xl border border-dashed border-border px-4 py-6 text-center text-sm text-muted-foreground">
            More markets for this match will appear here once the bookmaker opens them.
          </p>
        )}
      </div>
    </div>
  );
}
