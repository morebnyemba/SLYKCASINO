'use client';

import Link from 'next/link';
import { useCallback, useEffect, useState } from 'react';
import { BsArrowDown, BsArrowUp, BsCheck2, BsClipboard, BsLink45Deg, BsPersonCircle } from 'react-icons/bs';
import { Badge, Btn, Drawer, EmptyState, Notice, cx, money, tableClass, tdClass, thClass, trClass } from '@/components/console/ui';
import { ImpersonateButton } from '@/components/players/impersonate';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';

// The match a ticket is on (null for old free-text bets).
interface Match { id: number; name: string; starts_at?: string | null; status?: string; score_home?: number | null; score_away?: number | null }
interface Leg { id: number; event: string; match?: Match | null; market_name?: string | null; outcome_label?: string | null; selection: string; odds: string; result: string }
export interface Ticket {
  ticket: string; kind: 'single' | 'multiple'; id: number; code?: string | null; player_id: number | null; username: string;
  stake: string; odds?: string; combined_odds?: string; status: string; payout: string; placed_at: string;
  settled_at?: string | null; cashed_out_at?: string | null;
  bonus?: string; bonus_percent?: string; cashout_paid?: string; stake_cashed_out?: string;
  event?: string; match?: Match | null; market_name?: string | null; outcome_label?: string | null; selection?: string;
  legs?: Leg[];
}
export interface TicketSummary {
  tickets: number; staked: string; returned: string; net: string; open: number; open_liability: string;
  by_status: Record<string, number>;
}
export interface TicketsResponse { results: Ticket[]; next_cursor: string | null; summary: TicketSummary }
interface TicketDetail extends Ticket {
  cashout?: { available: boolean; value: string | null; reason: string } | null;
  player: { id: number; username: string; email: string; full_name: string; is_suspended: boolean; kyc_status: string; balance: string } | null;
}

export const STATUS_TONE: Record<string, 'gold' | 'green' | 'red' | 'slate' | 'indigo'> = {
  open: 'gold', pending: 'gold', accepting: 'gold', won: 'green', lost: 'red', void: 'slate', cashed_out: 'indigo', rejected: 'red',
};
const LEG_DOT: Record<string, string> = {
  won: 'bg-win', lost: 'bg-live', void: 'bg-muted-foreground/50', pending: 'bg-transparent ring-1 ring-inset ring-gold',
};
export const statusLabel = (s: string) => s.replace('_', ' ');

const pick = (x: { match?: Match | null; event?: string; market_name?: string | null; outcome_label?: string | null; selection?: string }) => ({
  match: x.match?.name || x.event || '—',
  score: x.match && x.match.score_home != null && x.match.score_away != null ? `${x.match.score_home}–${x.match.score_away}` : null,
  pick: [x.market_name, x.outcome_label || x.selection].filter(Boolean).join(': '),
});

const oddsOf = (t: Ticket) => Number(t.odds ?? t.combined_odds ?? 0);
/** What the ticket pays if it wins (multi-bet bonus included). */
export const potentialOf = (t: Ticket) => Number(t.stake) * oddsOf(t) * (1 + Number(t.bonus_percent ?? 0) / 100);
export const returnedOf = (t: Ticket) => Number(t.payout) + Number(t.cashout_paid ?? 0);

export function ago(iso: string) {
  const s = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  if (s < 7 * 86400) return `${Math.floor(s / 86400)}d ago`;
  return new Date(iso).toLocaleDateString();
}
const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString() : '—');

/** Copy text, showing a tick for a moment. */
function useCopy() {
  const [copied, setCopied] = useState<string | null>(null);
  const copy = useCallback((text: string, key = text) => {
    void navigator.clipboard?.writeText(text).then(() => {
      setCopied(key);
      window.setTimeout(() => setCopied((c) => (c === key ? null : c)), 1400);
    });
  }, []);
  return { copied, copy };
}

/** Tickets as players see them (#S12 single, #M5 multiple). Click a row to open it. */
export function TicketsTable({ tickets, showPlayer = true, active, onOpen }: {
  tickets: Ticket[]; showPlayer?: boolean; active?: string | null; onOpen: (ticket: string) => void;
}) {
  if (tickets.length === 0) return <EmptyState title="No tickets">Nothing matches these filters.</EmptyState>;
  return (
    <div className="overflow-x-auto">
      <table className={tableClass}>
        <thead><tr>
          <th className={thClass}>Ticket</th>{showPlayer && <th className={thClass}>Player</th>}
          <th className={thClass}>Selection</th><th className={cx(thClass, 'text-right')}>Stake</th><th className={cx(thClass, 'text-right')}>Odds</th>
          <th className={cx(thClass, 'text-right')}>Return</th><th className={thClass}>Status</th><th className={thClass}>Placed</th>
        </tr></thead>
        <tbody>
          {tickets.map((t) => {
            const multi = t.kind === 'multiple';
            const one = pick(t);
            const returned = returnedOf(t);
            const legs = t.legs ?? [];
            const isOpen = ['open', 'pending', 'accepting'].includes(t.status);
            return (
              <tr key={t.ticket} data-ticket={t.ticket} onClick={() => onOpen(t.ticket)}
                className={cx(trClass, 'cursor-pointer', active === t.ticket && 'bg-secondary/10 hover:bg-secondary/15')}>
                <td className={cx(tdClass, 'whitespace-nowrap')}>
                  <span className="font-mono text-xs font-bold">#{t.ticket}</span>
                  <p className="text-[11px] text-muted-foreground">{multi ? `Multiple · ${legs.length}` : 'Single'}</p>
                </td>
                {showPlayer && (
                  <td className={cx(tdClass, 'whitespace-nowrap')}>
                    {t.player_id ? (
                      <Link href={`/players/${t.player_id}`} onClick={(e) => e.stopPropagation()} className="font-semibold hover:text-secondary hover:underline">
                        {t.username}
                      </Link>
                    ) : '—'}
                  </td>
                )}
                <td className={cx(tdClass, 'max-w-[340px]')}>
                  {multi ? (
                    <>
                      <p className="truncate font-semibold">{legs.slice(0, 2).map((l) => pick(l).match).join(' · ')}{legs.length > 2 && ` +${legs.length - 2}`}</p>
                      <div className="mt-1 flex items-center gap-1" title={legs.map((l) => `${pick(l).match}: ${l.result}`).join('\n')}>
                        {legs.map((l) => <span key={l.id} className={cx('h-2 w-2 rounded-full', LEG_DOT[l.result] ?? LEG_DOT.pending)} />)}
                        <span className="ml-1 text-[11px] text-muted-foreground">
                          {legs.filter((l) => l.result === 'won').length}/{legs.length} won
                        </span>
                      </div>
                    </>
                  ) : (
                    <>
                      <p className="truncate font-semibold">{one.match}{one.score && <span className="ml-1.5 font-mono text-xs text-muted-foreground">{one.score}</span>}</p>
                      <p className="truncate text-xs text-muted-foreground">{one.pick}</p>
                    </>
                  )}
                </td>
                <td className={cx(tdClass, 'text-right tabular-nums')}>{money(t.stake)}</td>
                <td className={cx(tdClass, 'text-right tabular-nums')}>{oddsOf(t).toFixed(2)}</td>
                <td className={cx(tdClass, 'whitespace-nowrap text-right tabular-nums')}>
                  {isOpen ? (
                    <span className="text-muted-foreground" title="Pays if it wins">{money(potentialOf(t))}</span>
                  ) : (
                    <span className={cx('font-semibold', returned > 0 && 'text-win')}>{returned > 0 ? money(returned) : '—'}</span>
                  )}
                  {Number(t.cashout_paid ?? 0) > 0 && <p className="text-[11px] text-muted-foreground">cashed out {money(t.cashout_paid)}</p>}
                </td>
                <td className={tdClass}><Badge tone={STATUS_TONE[t.status] ?? 'slate'} dot>{statusLabel(t.status)}</Badge></td>
                <td className={cx(tdClass, 'whitespace-nowrap text-xs text-muted-foreground')} title={when(t.placed_at)}>{ago(t.placed_at)}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/** Tickets for a query string (null: not yet), with "load more" over the cursor. */
export function useTicketList(query: string | null) {
  const { accessToken } = useAuth();
  const first = useApi<TicketsResponse>(query === null ? null : `/admin/tickets/?${query}`);
  const [more, setMore] = useState<{ rows: Ticket[]; cursor: string | null } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { setMore(null); }, [query, first.data]);

  const rows = [...(first.data?.results ?? []), ...(more?.rows ?? [])];
  const cursor = more ? more.cursor : first.data?.next_cursor ?? null;
  const loadMore = useCallback(async () => {
    if (!cursor || !accessToken || query === null) return;
    setLoadingMore(true);
    setError('');
    const res = await authedRequest<TicketsResponse>('GET', `/admin/tickets/?${query}&cursor=${encodeURIComponent(cursor)}`, accessToken);
    setLoadingMore(false);
    if (!res.data) { setError(res.error ?? 'Could not load more tickets.'); return; }
    const page = res.data;
    setMore((m) => ({ rows: [...(m?.rows ?? []), ...page.results], cursor: page.next_cursor }));
  }, [cursor, accessToken, query]);

  return {
    rows, summary: first.data?.summary ?? null, hasMore: !!cursor, loadMore, loadingMore, error: error || first.error,
    loading: first.loading && !first.data, refreshing: first.loading, refetch: first.refetch,
  };
}

/** One ticket in full, in a side panel: money, every selection, timeline and the player. */
export function TicketDrawer({ ticket, onClose, onStep, hidePlayer }: {
  ticket: string | null; onClose: () => void; onStep?: (dir: 1 | -1) => void; hidePlayer?: boolean;
}) {
  const { data: t, loading, error } = useApi<TicketDetail>(ticket ? `/admin/tickets/${ticket}/` : null);
  const { copied, copy } = useCopy();
  const ready = t && t.ticket === ticket;
  const isOpen = ready && ['open', 'pending', 'accepting'].includes(t.status);
  const legs: Leg[] = !ready ? [] : t.kind === 'multiple' ? (t.legs ?? []) : [{
    id: t.id, event: t.event ?? '', match: t.match, market_name: t.market_name, outcome_label: t.outcome_label,
    selection: t.selection ?? '', odds: t.odds ?? '0', result: isOpen ? 'pending' : t.status,
  }];

  return (
    <Drawer
      open={!!ticket}
      onClose={onClose}
      title={`Ticket #${ticket ?? ''}`}
      description={ready ? `${t.kind === 'multiple' ? `Multiple · ${legs.length} selections` : 'Single'}${t.code ? ` · code ${t.code}` : ''} · placed ${when(t.placed_at)}` : 'Loading…'}
      footer={(
        <div className="flex w-full flex-wrap items-center gap-2">
          {onStep && (
            <>
              <Btn size="sm" variant="ghost" icon={BsArrowUp} onClick={() => onStep(-1)} title="Previous ticket (k)">Prev</Btn>
              <Btn size="sm" variant="ghost" icon={BsArrowDown} onClick={() => onStep(1)} title="Next ticket (j)">Next</Btn>
            </>
          )}
          <span className="flex-1" />
          <Btn size="sm" icon={copied === 'id' ? BsCheck2 : BsClipboard} onClick={() => ticket && copy(ticket, 'id')}>
            {copied === 'id' ? 'Copied' : 'Copy number'}
          </Btn>
          <Btn size="sm" icon={copied === 'link' ? BsCheck2 : BsLink45Deg}
            onClick={() => ticket && copy(`${window.location.origin}/admin-portal/tickets?ticket=${ticket}`, 'link')}>
            {copied === 'link' ? 'Copied' : 'Copy link'}
          </Btn>
        </div>
      )}
    >
      {error && !ready ? <Notice tone="red">Could not load this ticket.</Notice> : !ready || loading ? (
        <div className="space-y-3">{[0, 1, 2].map((i) => <div key={i} className="h-20 animate-pulse rounded-xl bg-muted/50" />)}</div>
      ) : (
        <div className="space-y-6">
          {/* Outcome */}
          <div className="rounded-2xl border border-border/70 bg-card p-4">
            <div className="flex items-center justify-between">
              <Badge tone={STATUS_TONE[t.status] ?? 'slate'} dot>{statusLabel(t.status)}</Badge>
              <span className="text-xs text-muted-foreground">{isOpen ? 'Pays if it wins' : 'Paid to player'}</span>
            </div>
            <p className={cx('mt-2 text-3xl font-extrabold tabular-nums', !isOpen && returnedOf(t) > 0 && 'text-win')}>
              {money(isOpen ? potentialOf(t) : returnedOf(t))}
            </p>
            <dl className="mt-4 grid grid-cols-3 gap-3 border-t border-border/60 pt-3 text-sm">
              <div><dt className="text-[11px] font-bold uppercase text-muted-foreground">Stake</dt><dd className="font-semibold tabular-nums">{money(t.stake)}</dd></div>
              <div><dt className="text-[11px] font-bold uppercase text-muted-foreground">Odds</dt><dd className="font-semibold tabular-nums">{oddsOf(t).toFixed(2)}</dd></div>
              <div>
                <dt className="text-[11px] font-bold uppercase text-muted-foreground">House</dt>
                <dd className={cx('font-semibold tabular-nums', isOpen ? 'text-muted-foreground' : Number(t.stake) + Number(t.stake_cashed_out ?? 0) - returnedOf(t) >= 0 ? 'text-win' : 'text-live')}>
                  {isOpen ? 'pending' : money(Number(t.stake) + Number(t.stake_cashed_out ?? 0) - returnedOf(t))}
                </dd>
              </div>
            </dl>
            {(Number(t.bonus_percent ?? 0) > 0 || Number(t.cashout_paid ?? 0) > 0) && (
              <div className="mt-3 space-y-1 text-xs text-muted-foreground">
                {Number(t.bonus_percent ?? 0) > 0 && <p>Multi-bet bonus {Number(t.bonus_percent)}%{Number(t.bonus ?? 0) > 0 && ` · paid ${money(t.bonus)}`}</p>}
                {Number(t.cashout_paid ?? 0) > 0 && <p>Cashed out {money(t.cashout_paid)} for {money(t.stake_cashed_out)} of the stake</p>}
              </div>
            )}
            {t.cashout?.available && t.cashout.value && (
              <p className="mt-3 rounded-lg bg-secondary/10 px-3 py-2 text-xs font-semibold text-secondary">Cash-out offer right now: {money(t.cashout.value)}</p>
            )}
          </div>

          {/* Selections */}
          <section>
            <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">Selections</h3>
            <ol className="space-y-2">
              {legs.map((leg, i) => {
                const l = pick(leg);
                return (
                  <li key={leg.id} className="flex items-start gap-3 rounded-xl border border-border/70 p-3">
                    <span className={cx('mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full', LEG_DOT[leg.result] ?? LEG_DOT.pending)} />
                    <div className="min-w-0 flex-1">
                      <p className="font-semibold">
                        {leg.match ? <Link href={`/sportsbook/matches/${leg.match.id}`} className="hover:underline">{l.match}</Link> : l.match}
                        {l.score && <span className="ml-2 font-mono text-xs text-muted-foreground">{l.score}</span>}
                      </p>
                      <p className="text-sm text-muted-foreground">{l.pick || '—'}</p>
                      {leg.match?.starts_at && (
                        <p className="mt-0.5 text-[11px] text-muted-foreground">
                          {legs.length > 1 && `Leg ${i + 1} · `}kick-off {when(leg.match.starts_at)}{leg.match.status && ` · ${leg.match.status.replace('_', ' ')}`}
                        </p>
                      )}
                    </div>
                    <div className="text-right">
                      <p className="font-mono text-sm font-bold">{Number(leg.odds).toFixed(2)}</p>
                      <Badge tone={STATUS_TONE[leg.result === 'pending' ? 'open' : leg.result] ?? 'slate'}>{leg.result}</Badge>
                    </div>
                  </li>
                );
              })}
            </ol>
          </section>

          {/* Timeline */}
          <section>
            <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">Timeline</h3>
            <ol className="relative space-y-3 border-l border-border pl-4 text-sm">
              <li><span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full bg-secondary" />Placed <span className="text-muted-foreground">· {when(t.placed_at)}</span></li>
              {t.cashed_out_at && <li><span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full bg-secondary" />Cashed out <span className="text-muted-foreground">· {when(t.cashed_out_at)}</span></li>}
              {t.settled_at && <li><span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full bg-secondary" />Settled as {statusLabel(t.status)} <span className="text-muted-foreground">· {when(t.settled_at)}</span></li>}
              {isOpen && <li className="text-muted-foreground"><span className="absolute -left-[5px] mt-1.5 h-2.5 w-2.5 rounded-full border border-gold bg-background" />Waiting for results</li>}
            </ol>
          </section>

          {/* Player */}
          {!hidePlayer && (
            <section>
              <h3 className="mb-2 text-[11px] font-bold uppercase tracking-wide text-muted-foreground">Player</h3>
              {t.player ? (
                <div className="rounded-xl border border-border/70 p-3">
                  <div className="flex items-center gap-3">
                    <BsPersonCircle size={28} className="text-muted-foreground" />
                    <div className="min-w-0 flex-1">
                      <p className="truncate font-bold">{t.player.full_name || t.player.username}
                        {t.player.is_suspended && <Badge tone="red" className="ml-2">suspended</Badge>}</p>
                      <p className="truncate text-xs text-muted-foreground">@{t.player.username} · {t.player.email || 'no email'} · KYC {t.player.kyc_status}</p>
                    </div>
                    <div className="text-right">
                      <p className="text-[11px] font-bold uppercase text-muted-foreground">Balance</p>
                      <p className="font-semibold tabular-nums">{money(t.player.balance)}</p>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-wrap gap-2">
                    <Link href={`/players/${t.player.id}`} className="inline-flex h-8 items-center rounded-xl border border-border px-3 text-xs font-semibold hover:border-secondary/60 hover:bg-muted/60">
                      Open profile
                    </Link>
                    <ImpersonateButton size="sm" playerId={t.player.id} username={t.player.username} />
                  </div>
                </div>
              ) : <p className="text-sm text-muted-foreground">The player who placed this ticket has been deleted.</p>}
            </section>
          )}
        </div>
      )}
    </Drawer>
  );
}

/** j/k (and the arrow keys while a ticket is open) step through `rows`. */
export function useTicketKeys(rows: Ticket[], active: string | null, setActive: (t: string | null) => void) {
  const step = useCallback((dir: 1 | -1) => {
    if (rows.length === 0) return;
    const i = rows.findIndex((r) => r.ticket === active);
    const next = rows[Math.min(rows.length - 1, Math.max(0, i === -1 ? 0 : i + dir))];
    setActive(next.ticket);
    document.querySelector(`[data-ticket="${next.ticket}"]`)?.scrollIntoView({ block: 'nearest' });
  }, [rows, active, setActive]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el.closest('input, textarea, select, [contenteditable]') || e.metaKey || e.ctrlKey || e.altKey) return;
      const arrows = active !== null;  // leave the arrows to page scrolling otherwise
      if (e.key === 'j' || (arrows && e.key === 'ArrowDown')) { e.preventDefault(); step(1); }
      if (e.key === 'k' || (arrows && e.key === 'ArrowUp')) { e.preventDefault(); step(-1); }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [step, active]);
  return step;
}

interface JetRow { id: number; round: number; stake: string; status: string; cashout_multiplier: string | null; payout: string; is_free?: boolean; created_at: string; crash_point: string | null }

/** A player's tickets, Aviator bets and withdrawals, for the player page. */
export function PlayerActivity({ playerId }: { playerId: number }) {
  const [tab, setTab] = useState<'tickets' | 'aviator' | 'withdrawals'>('tickets');
  const tickets = useTicketList(`player_id=${playerId}&limit=25`);
  const [active, setActive] = useState<string | null>(null);
  const step = useTicketKeys(tab === 'tickets' ? tickets.rows : [], active, setActive);
  const jet = useApi<{ results: JetRow[]; summary: { bets: number; staked: string; won: string; net: string } }>(tab === 'aviator' ? `/admin/jet/bets/?player_id=${playerId}` : null);
  const wd = useApi<{ results: { id: number; amount: string; method_label: string; account_number: string; status: string; status_label: string; reference: string; note: string; created_at: string }[] }>(
    tab === 'withdrawals' ? `/admin/withdrawals/?status=all&player_id=${playerId}` : null);
  const s = tickets.summary;
  return (
    <div className="overflow-hidden rounded-2xl border border-border/70 bg-card">
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
        {([['tickets', 'Sportsbook tickets'], ['aviator', 'Aviator bets'], ['withdrawals', 'Withdrawals']] as const).map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)}
            className={cx('rounded-lg px-3 py-1.5 text-sm font-semibold', tab === id ? 'bg-secondary text-secondary-foreground' : 'text-muted-foreground hover:bg-muted')}>
            {label}
          </button>
        ))}
        {tab === 'tickets' && s && (
          <p className="ml-auto text-xs text-muted-foreground">
            {s.tickets} tickets · {s.open} open ({money(s.open_liability)} riding) · staked {money(s.staked)} · returned {money(s.returned)} · house {money(s.net)}
          </p>
        )}
        {tab === 'aviator' && jet.data && (
          <p className="ml-auto text-xs text-muted-foreground">{jet.data.summary.bets} bets · staked {money(jet.data.summary.staked)} · won {money(jet.data.summary.won)} · net {money(jet.data.summary.net)}</p>
        )}
      </div>
      {tab === 'tickets' && (tickets.loading ? <div className="h-32 animate-pulse bg-muted/40" /> : (
        <>
          <TicketsTable tickets={tickets.rows} showPlayer={false} active={active} onOpen={setActive} />
          {tickets.hasMore && (
            <div className="flex justify-center border-t border-border/60 p-3">
              <Btn size="sm" busy={tickets.loadingMore} onClick={() => void tickets.loadMore()}>Load more</Btn>
            </div>
          )}
          <TicketDrawer ticket={active} onClose={() => setActive(null)} onStep={step} hidePlayer />
        </>
      ))}
      {tab === 'aviator' && (
        (jet.data?.results ?? []).length === 0 ? <EmptyState title="No Aviator bets">This player hasn’t played Aviator.</EmptyState> : (
          <div className="overflow-x-auto">
            <table className={tableClass}>
              <thead><tr><th className={thClass}>Round</th><th className={thClass}>Stake</th><th className={thClass}>Cashed at</th><th className={thClass}>Crash</th><th className={thClass}>Won</th><th className={thClass}>Status</th><th className={thClass}>Time</th></tr></thead>
              <tbody>
                {jet.data!.results.map((b) => (
                  <tr key={b.id} className={trClass}>
                    <td className={cx(tdClass, 'font-mono text-xs')}>#{b.round}</td>
                    <td className={cx(tdClass, 'tabular-nums')}>{money(b.stake)}{b.is_free && <Badge tone="gold">free</Badge>}</td>
                    <td className={cx(tdClass, 'tabular-nums')}>{b.cashout_multiplier ? `${Number(b.cashout_multiplier).toFixed(2)}x` : '—'}</td>
                    <td className={cx(tdClass, 'tabular-nums text-muted-foreground')}>{b.crash_point ? `${Number(b.crash_point).toFixed(2)}x` : '…'}</td>
                    <td className={cx(tdClass, 'font-semibold tabular-nums', Number(b.payout) > 0 && 'text-win')}>{Number(b.payout) > 0 ? money(b.payout) : '—'}</td>
                    <td className={tdClass}><Badge tone={STATUS_TONE[b.status === 'cashed' ? 'won' : b.status] ?? 'slate'}>{b.status}</Badge></td>
                    <td className={cx(tdClass, 'whitespace-nowrap text-xs text-muted-foreground')}>{new Date(b.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
      {tab === 'withdrawals' && (
        (wd.data?.results ?? []).length === 0 ? <EmptyState title="No withdrawals">This player hasn’t asked to withdraw.</EmptyState> : (
          <div className="overflow-x-auto">
            <table className={tableClass}>
              <thead><tr><th className={thClass}>#</th><th className={thClass}>Amount</th><th className={thClass}>To</th><th className={thClass}>Status</th><th className={thClass}>Requested</th></tr></thead>
              <tbody>
                {wd.data!.results.map((w) => (
                  <tr key={w.id} className={trClass}>
                    <td className={cx(tdClass, 'font-mono text-xs')}>W{w.id}</td>
                    <td className={cx(tdClass, 'font-semibold tabular-nums')}>{money(w.amount)}</td>
                    <td className={tdClass}>{w.method_label} <span className="font-mono text-xs text-muted-foreground">{w.account_number}</span></td>
                    <td className={tdClass}>{w.status_label}{(w.reference || w.note) && <p className="text-xs text-muted-foreground">{w.reference || w.note}</p>}</td>
                    <td className={cx(tdClass, 'whitespace-nowrap text-xs text-muted-foreground')}>{new Date(w.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  );
}
