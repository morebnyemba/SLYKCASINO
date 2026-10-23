'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { BsArrowRight, BsDownload, BsFunnel, BsUpcScan, BsXLg } from 'react-icons/bs';
import { BetTicket, money, ticketFromRow, type ApiBet, type ApiSlip, type Ticket } from '@/components/bet-ticket';
import { useCashoutOffers } from '@/components/cashout';
import { useAuth } from '@/lib/auth-context';
import { authedGet, useApi } from '@/lib/use-api';
import { LoadingState, Spinner } from '@slyk/ui/components/spinner';

type Tab = 'all' | 'open' | 'live' | 'settled';
type Row = (ApiBet | ApiSlip) & { kind: 'single' | 'multiple' };
interface Page {
  results: Row[];
  next_cursor: string | null;
  counts: Partial<Record<Tab, number>>;
  stats: { staked: string; returned: string; net: string; won: number; decided: number } | null;
}

const TABS: { key: Tab; label: string }[] = [
  { key: 'all', label: 'All' }, { key: 'open', label: 'Open' }, { key: 'live', label: 'Live' }, { key: 'settled', label: 'Settled' },
];
const PAGE = 20;

function Stat({ label, value, className = '' }: { label: string; value: string; className?: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-border bg-card px-3 py-2.5">
      <p className="truncate text-[10.5px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={`truncate text-[15px] font-extrabold tabular-nums sm:text-lg ${className}`}>{value}</p>
    </div>
  );
}

export default function MyBetsPage() {
  const { accessToken } = useAuth();
  const [tab, setTab] = useState<Tab>('all');
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [showFilters, setShowFilters] = useState(false);

  const query = useMemo(() => {
    const p = new URLSearchParams({ tab, limit: String(PAGE) });
    if (fromDate) p.set('date_from', fromDate);
    if (toDate) p.set('date_to', toDate);
    return p.toString();
  }, [tab, fromDate, toDate]);
  const first = useApi<Page>(`/my-tickets/?${query}`);

  // Older pages ("Load more"), kept while the first page refreshes.
  const [extra, setExtra] = useState<{ rows: Row[]; cursor: string | null } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  useEffect(() => { setExtra(null); }, [query]);
  const cursor = extra ? extra.cursor : first.data?.next_cursor ?? null;
  const loadMore = useCallback(async () => {
    if (!cursor || !accessToken) return;
    setLoadingMore(true);
    const res = await authedGet<Page>(`/my-tickets/?${query}&cursor=${encodeURIComponent(cursor)}`, accessToken);
    setLoadingMore(false);
    if (res.data) {
      const page = res.data;
      setExtra((e) => ({ rows: [...(e?.rows ?? []), ...page.results], cursor: page.next_cursor }));
    }
  }, [cursor, accessToken, query]);

  const tickets: Ticket[] = useMemo(() => {
    const seen = new Set<string>();
    return [...(first.data?.results ?? []), ...(extra?.rows ?? [])].map(ticketFromRow)
      .filter((t) => (seen.has(t.key) ? false : (seen.add(t.key), true)));
  }, [first.data, extra]);
  const offers = useCashoutOffers(tickets);
  const counts = first.data?.counts ?? {};
  const stats = first.data?.stats;

  // Live: scores, results and settlements refresh every 15s while a ticket is still running.
  const { refetch } = first;
  const running = (counts.open ?? 0) > 0;
  useEffect(() => {
    if (!running || tab === 'settled') return;
    const t = window.setInterval(() => { if (document.visibilityState === 'visible') refetch(); }, 15_000);
    return () => window.clearInterval(t);
  }, [running, tab, refetch]);

  function exportCsv() {
    const esc = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`;
    const header = 'Ticket,Code,Type,Selections,Stake,Odds,Payout,Status,Placed\n';
    const rows = tickets.map((t) => [
      `${t.kind === 'single' ? 'S' : 'M'}${t.id}`, t.code ?? '', t.kind,
      t.legs.map((l) => `${l.match} - ${l.pick} @ ${l.odds.toFixed(2)}`).join(' | '),
      (t.status === 'cashed_out' ? t.stakeCashedOut : t.stake + t.stakeCashedOut).toFixed(2), t.odds.toFixed(2),
      t.payout?.toFixed(2) ?? '', t.status, t.placedAt,
    ].map(esc).join(','));
    const url = URL.createObjectURL(new Blob([header + rows.join('\n')], { type: 'text/csv' }));
    Object.assign(document.createElement('a'), { href: url, download: 'my-bets.csv' }).click();
    URL.revokeObjectURL(url);
  }

  const filtered = !!(fromDate || toDate);
  const net = Number(stats?.net ?? 0);

  return (
    <div>
      <div className="mb-3 flex items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">My Bets</h1>
        <div className="flex items-center gap-1.5">
          <Link href="/check-ticket" className="flex items-center gap-1.5 rounded-lg border border-border px-2.5 py-1.5 text-xs font-bold hover:bg-muted">
            <BsUpcScan size={13} /> <span className="hidden sm:inline">Check a ticket</span><span className="sm:hidden">Check</span>
          </Link>
          <button onClick={() => setShowFilters((v) => !v)} aria-expanded={showFilters}
            className={`flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-xs font-bold ${filtered ? 'border-secondary text-secondary' : 'border-border hover:bg-muted'}`}>
            <BsFunnel size={12} /> Filter{filtered && ' ·1'}
          </button>
        </div>
      </div>

      {showFilters && (
        <div className="mb-3 flex flex-wrap items-center gap-2 rounded-xl border border-border bg-card p-3 text-xs">
          <span className="font-semibold text-muted-foreground">Placed</span>
          <input type="date" value={fromDate} max={toDate || undefined} onChange={(e) => setFromDate(e.target.value)} aria-label="From date"
            className="rounded-md border border-border bg-background px-2 py-1" />
          <span className="text-muted-foreground">to</span>
          <input type="date" value={toDate} min={fromDate || undefined} onChange={(e) => setToDate(e.target.value)} aria-label="To date"
            className="rounded-md border border-border bg-background px-2 py-1" />
          {filtered && (
            <button onClick={() => { setFromDate(''); setToDate(''); }} className="flex items-center gap-1 font-bold text-muted-foreground hover:text-foreground">
              <BsXLg size={10} /> Clear
            </button>
          )}
          <button onClick={exportCsv} disabled={tickets.length === 0}
            className="ml-auto flex items-center gap-1.5 rounded-md border border-border px-2.5 py-1 font-semibold text-muted-foreground hover:bg-muted disabled:opacity-50">
            <BsDownload size={11} /> Export CSV
          </button>
        </div>
      )}

      {stats && (counts.all ?? 0) > 0 && (
        <div className="mb-3 grid grid-cols-3 gap-2">
          <Stat label="Staked" value={money(Number(stats.staked))} />
          <Stat label="Returned" value={money(Number(stats.returned))} className="text-win" />
          <Stat label={net >= 0 ? 'Profit' : 'Loss'} value={`${net >= 0 ? '+' : '−'}${money(Math.abs(net))}`}
            className={net >= 0 ? 'text-win' : 'text-muted-foreground'} />
        </div>
      )}

      {/* Stays in reach while scrolling a long list. */}
      <div className="sticky top-[var(--header-h)] z-20 -mx-3 mb-3 bg-background/95 px-3 py-2 backdrop-blur sm:mx-0 sm:px-0">
        <div className="flex rounded-lg border border-border bg-card p-0.5" role="tablist">
          {TABS.map(({ key, label }) => {
            const n = counts[key];
            return (
              <button key={key} role="tab" aria-selected={tab === key} onClick={() => setTab(key)}
                className={`flex flex-1 items-center justify-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-bold transition-colors ${
                  tab === key ? 'bg-secondary text-secondary-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
                {key === 'live' && (n ?? 0) > 0 && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-live" />}
                {label}
                {key !== 'all' && n != null && n > 0 && <span className="tabular-nums opacity-80">{n}</span>}
              </button>
            );
          })}
        </div>
      </div>

      {first.loading && !first.data ? (
        <LoadingState />
      ) : first.error && !first.data ? (
        <p className="text-sm text-destructive">Couldn’t load your bets. <button onClick={refetch} className="underline">Try again</button></p>
      ) : tickets.length === 0 ? (
        <div className="rounded-xl border border-border bg-card px-6 py-10 text-center">
          <p className="font-bold">
            {(counts.all ?? 0) === 0 && !filtered ? 'No bets yet'
              : tab === 'live' ? 'Nothing playing right now' : tab === 'open' ? 'No open bets' : filtered ? 'No bets in these dates' : 'No settled bets yet'}
          </p>
          <p className="mt-1 text-sm text-muted-foreground">
            {tab === 'live' ? 'Tickets show up here while one of their matches is being played.' : 'Your bets show up here as tickets.'}
          </p>
          <Link href="/sportsbook" className="mt-4 inline-flex items-center gap-1.5 rounded-lg bg-win px-4 py-2 text-sm font-extrabold text-win-foreground">
            Browse matches <BsArrowRight size={12} />
          </Link>
        </div>
      ) : (
        <>
          <div className="grid items-start gap-2.5 md:grid-cols-2">
            {tickets.map((t) => (
              <BetTicket key={t.key} ticket={t} offer={offers[t.key]} onChanged={refetch} collapsible />
            ))}
          </div>
          {cursor && (
            <div className="mt-4 flex justify-center">
              <button onClick={() => void loadMore()} disabled={loadingMore}
                className="flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-bold hover:bg-muted disabled:opacity-60">
                {loadingMore && <Spinner size={13} />} Show older bets
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
