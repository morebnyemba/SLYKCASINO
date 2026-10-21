'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import {
  BsArrowClockwise, BsCashCoin, BsDownload, BsGraphUpArrow, BsHourglassSplit, BsSearch, BsTicketPerforated, BsXLg,
} from 'react-icons/bs';
import {
  Btn, Notice, PageHeader, Panel, StatTile, Switch, Tabs, cx, inputClass, money,
} from '@/components/console/ui';
import {
  STATUS_TONE, TicketDrawer, TicketsTable, potentialOf, returnedOf, statusLabel, useTicketKeys, useTicketList, type Ticket,
} from '@/components/tickets/tickets';

interface Filters { q: string; status: string; kind: string; date_from: string; date_to: string; min_stake: string }
const EMPTY: Filters = { q: '', status: '', kind: '', date_from: '', date_to: '', min_stake: '' };
const KEYS = Object.keys(EMPTY) as (keyof Filters)[];
// Tab order; any other status that shows up in the counts goes after these.
const STATUS_ORDER = ['open', 'won', 'lost', 'cashed_out', 'void', 'accepting', 'pending', 'rejected'];

const day = (offset = 0) => {
  const d = new Date();
  d.setDate(d.getDate() - offset);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};
// A compact input for the filter row (inputClass is full-width).
const compact = 'h-8 rounded-lg border border-border bg-input/60 px-2.5 text-xs text-foreground outline-none focus:border-secondary focus:ring-2 focus:ring-secondary/30';
const PRESETS = [
  { id: 'today', label: 'Today', from: () => day(), to: () => day() },
  { id: '7d', label: '7 days', from: () => day(6), to: () => '' },
  { id: '30d', label: '30 days', from: () => day(29), to: () => '' },
];

function toCsv(rows: Ticket[]) {
  const head = ['ticket', 'type', 'player', 'selection', 'stake', 'odds', 'potential', 'returned', 'status', 'placed_at', 'settled_at'];
  const esc = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
  const lines = rows.map((t) => [
    t.ticket, t.kind, t.username,
    t.kind === 'multiple' ? (t.legs ?? []).map((l) => `${l.match?.name || l.event} (${l.outcome_label || l.selection})`).join(' | ')
      : `${t.match?.name || t.event} (${[t.market_name, t.outcome_label || t.selection].filter(Boolean).join(': ')})`,
    t.stake, t.odds ?? t.combined_odds, potentialOf(t).toFixed(2), returnedOf(t).toFixed(2), t.status, t.placed_at, t.settled_at ?? '',
  ].map(esc).join(','));
  return [head.join(','), ...lines].join('\n');
}

/** Every player's tickets: search, filter, open one in full, and step through them with j/k. */
export default function TicketsPage() {
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [q, setQ] = useState('');
  const [active, setActive] = useState<string | null>(null);
  const [live, setLive] = useState(false);
  const [ready, setReady] = useState(false);
  const search = useRef<HTMLInputElement>(null);

  // Filters and the open ticket live in the URL, so a view can be shared or bookmarked.
  // (Read on mount rather than with useSearchParams, which needs a Suspense boundary.)
  useEffect(() => {
    const p = new URLSearchParams(window.location.search);
    const f = { ...EMPTY };
    for (const k of KEYS) f[k] = p.get(k) ?? '';
    setFilters(f);
    setQ(f.q);
    setActive(p.get('ticket'));
    setReady(true);
  }, []);
  useEffect(() => {
    if (!ready) return;
    const p = new URLSearchParams();
    for (const k of KEYS) if (filters[k]) p.set(k, filters[k]);
    if (active) p.set('ticket', active);
    const qs = p.toString();
    window.history.replaceState(null, '', `${window.location.pathname}${qs ? `?${qs}` : ''}`);
  }, [filters, active, ready]);

  // Search as the operator types.
  useEffect(() => {
    const t = window.setTimeout(() => setFilters((f) => (f.q === q.trim() ? f : { ...f, q: q.trim() })), 300);
    return () => window.clearTimeout(t);
  }, [q]);

  // "/" jumps to search.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key !== '/' || (e.target as HTMLElement).closest('input, textarea, select')) return;
      e.preventDefault();
      search.current?.focus();
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, []);

  const query = useMemo(() => {
    const p = new URLSearchParams({ limit: '50' });
    for (const k of KEYS) if (filters[k]) p.set(k, filters[k]);
    return p.toString();
  }, [filters]);
  const list = useTicketList(ready ? query : null);
  const step = useTicketKeys(list.rows, active, setActive);

  // Live mode: refresh the first page every 15s (paused while older pages are loaded).
  const { refetch, hasMore } = list;
  const extraPages = list.rows.length > 50;
  useEffect(() => {
    if (!live || extraPages) return;
    const t = window.setInterval(refetch, 15_000);
    return () => window.clearInterval(t);
  }, [live, extraPages, refetch]);

  const set = (patch: Partial<Filters>) => setFilters((f) => ({ ...f, ...patch }));
  const s = list.summary;
  const counts = s?.by_status ?? {};
  const allCount = Object.values(counts).reduce((a, b) => a + b, 0);
  const statusTabs = [
    { id: '', label: 'All', count: allCount },
    ...[...STATUS_ORDER, ...Object.keys(counts).filter((k) => !STATUS_ORDER.includes(k))]
      .filter((k) => counts[k] || filters.status === k || ['open', 'won', 'lost'].includes(k))
      .map((k) => ({ id: k, label: statusLabel(k), count: counts[k] ?? 0, tone: k === 'open' && counts[k] ? ('red' as const) : undefined })),
  ];
  const preset = PRESETS.find((p) => p.from() === filters.date_from && p.to() === filters.date_to)?.id;
  const filtered = KEYS.some((k) => k !== 'status' && filters[k]);

  function exportCsv() {
    const url = URL.createObjectURL(new Blob([toCsv(list.rows)], { type: 'text/csv' }));
    const a = Object.assign(document.createElement('a'), { href: url, download: `tickets-${day()}.csv` });
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-5">
      <PageHeader
        icon={BsTicketPerforated} eyebrow="Sportsbook" title="Tickets"
        description="Every player’s singles (#S…) and multiples (#M…), newest first. Click a ticket for the full picture."
        actions={(
          <>
            <label className="flex items-center gap-2 text-xs font-semibold text-muted-foreground">
              <Switch checked={live} onChange={setLive} label="Auto-refresh" /> Auto-refresh
            </label>
            <Btn icon={BsArrowClockwise} busy={list.refreshing && !list.loading} onClick={refetch}>Refresh</Btn>
            <Btn icon={BsDownload} disabled={list.rows.length === 0} onClick={exportCsv} title="Exports the tickets loaded below">CSV</Btn>
          </>
        )}
      />

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="Tickets" icon={BsTicketPerforated} loading={!s} value={s?.tickets.toLocaleString() ?? '—'}
          hint={s && `${money(s.staked)} staked`} />
        <StatTile label="Paid out" icon={BsCashCoin} tone="gold" loading={!s} value={s ? money(s.returned) : '—'} hint="Winnings and cash-outs" />
        <StatTile label="House result" icon={BsGraphUpArrow} tone={s && Number(s.net) < 0 ? 'red' : 'green'} loading={!s}
          value={s ? money(s.net) : '—'} hint={s && Number(s.staked) > 0 ? `${((Number(s.net) / Number(s.staked)) * 100).toFixed(1)}% hold` : 'Staked minus paid out'} />
        <StatTile label="Open" icon={BsHourglassSplit} tone="red" loading={!s} value={s?.open.toLocaleString() ?? '—'}
          hint={s && `${money(s.open_liability)} riding if they all win`} />
      </div>

      <Panel padded={false}>
        <div className="space-y-3 border-b border-border/60 p-4">
          <div className="flex flex-wrap items-center gap-2">
            <div className="relative min-w-[240px] flex-1">
              <BsSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={14} />
              <input ref={search} value={q} onChange={(e) => setQ(e.target.value)} className={cx(inputClass, 'pl-9 pr-9')}
                placeholder="Ticket (S12, M5), username, email or name   ·   press / to search"
                onKeyDown={(e) => { if (e.key === 'Escape') setQ(''); }} />
              {q && (
                <button onClick={() => setQ('')} aria-label="Clear search" className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                  <BsXLg size={12} />
                </button>
              )}
            </div>
            <div className="flex rounded-xl border border-border p-0.5" role="group" aria-label="Ticket type">
              {[['', 'All'], ['single', 'Singles'], ['multiple', 'Multiples']].map(([id, label]) => (
                <button key={id} onClick={() => set({ kind: id })}
                  className={cx('rounded-lg px-3 py-1.5 text-xs font-semibold', filters.kind === id ? 'bg-secondary text-white' : 'text-muted-foreground hover:bg-muted')}>
                  {label}
                </button>
              ))}
            </div>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            {PRESETS.map((p) => (
              <button key={p.id} onClick={() => set(preset === p.id ? { date_from: '', date_to: '' } : { date_from: p.from(), date_to: p.to() })}
                className={cx('rounded-full border px-3 py-1 text-xs font-semibold', preset === p.id ? 'border-secondary bg-secondary/10 text-secondary' : 'border-border text-muted-foreground hover:bg-muted')}>
                {p.label}
              </button>
            ))}
            <input type="date" aria-label="From" value={filters.date_from} max={filters.date_to || undefined}
              onChange={(e) => set({ date_from: e.target.value })} className={compact} />
            <span className="text-xs text-muted-foreground">to</span>
            <input type="date" aria-label="To" value={filters.date_to} min={filters.date_from || undefined}
              onChange={(e) => set({ date_to: e.target.value })} className={compact} />
            <input type="number" min="0" step="1" inputMode="decimal" aria-label="Minimum stake" placeholder="Min stake $"
              value={filters.min_stake} onChange={(e) => set({ min_stake: e.target.value })} className={cx(compact, 'w-28')} />
            {filtered && <Btn size="sm" variant="ghost" icon={BsXLg} onClick={() => { setQ(''); setFilters({ ...EMPTY, status: filters.status }); }}>Clear filters</Btn>}
          </div>
          <Tabs value={filters.status} onChange={(status) => set({ status })} items={statusTabs} />
        </div>

        {list.error && <div className="p-4"><Notice tone="red">Could not load tickets: {list.error}</Notice></div>}
        {list.loading ? (
          <div className="space-y-px">{Array.from({ length: 8 }, (_, i) => <div key={i} className="h-14 animate-pulse bg-muted/30" />)}</div>
        ) : (
          <div className={cx('transition-opacity', list.refreshing && 'opacity-60')}>
            <TicketsTable tickets={list.rows} active={active} onOpen={setActive} />
          </div>
        )}

        <div className="flex flex-wrap items-center justify-between gap-3 border-t border-border/60 px-4 py-3 text-xs text-muted-foreground">
          <span>
            Showing {list.rows.length.toLocaleString()}{s ? ` of ${s.tickets.toLocaleString()}` : ''}
            {filters.status && <> · <span className={cx('font-semibold', STATUS_TONE[filters.status] === 'red' && 'text-live')}>{statusLabel(filters.status)}</span></>}
          </span>
          <span className="hidden sm:inline">
            <kbd className="rounded border border-border px-1">j</kbd> <kbd className="rounded border border-border px-1">k</kbd> step through ·{' '}
            <kbd className="rounded border border-border px-1">/</kbd> search · <kbd className="rounded border border-border px-1">Esc</kbd> close
          </span>
          {hasMore && <Btn size="sm" busy={list.loadingMore} onClick={() => void list.loadMore()}>Load 50 more</Btn>}
        </div>
      </Panel>

      <TicketDrawer ticket={active} onClose={() => setActive(null)} onStep={step} />
    </div>
  );
}
