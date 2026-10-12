'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { BsChevronLeft, BsChevronRight, BsSearch } from 'react-icons/bs';
import { FaExchangeAlt } from 'react-icons/fa';
import { Btn, EmptyState, Notice, PageHeader, TextInput, cx, tableClass, tdClass, thClass, trClass } from '@/components/console/ui';
import { KIND_FILTERS, kindLabel, kindTone } from '@/lib/ledger-kinds';
import { useApi } from '@/lib/use-api';

interface LedgerEntry {
  id: number; amount: string; kind: string; reference: string; idempotency_key: string;
  created_at: string; player_id: number; username: string | null;
}
interface LedgerResponse { count: number; next: string | null; previous: string | null; results: LedgerEntry[] }

const PAGE_SIZES = [25, 50, 100, 200];
const select = 'h-10 rounded-xl border border-border bg-background px-3 text-sm';

/** Every wallet movement, newest first: search, filter by type and date, and page through. */
export default function TransactionsPage() {
  const [q, setQ] = useState('');
  const [search, setSearch] = useState('');
  const [kind, setKind] = useState('');
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [pageSize, setPageSize] = useState(50);
  const [page, setPage] = useState(1);

  // Search as you type, after a short pause.
  useEffect(() => {
    const t = window.setTimeout(() => { setSearch(q.trim()); setPage(1); }, 350);
    return () => window.clearTimeout(t);
  }, [q]);

  const params = new URLSearchParams({
    page: String(page), page_size: String(pageSize),
    ...(search && { q: search }), ...(kind && { kind }), ...(from && { date_from: from }), ...(to && { date_to: to }),
  });
  const { data, loading, error } = useApi<LedgerResponse>(`/admin/ledger/?${params}`);
  const entries = data?.results ?? [];
  const pages = data ? Math.max(1, Math.ceil(data.count / pageSize)) : 1;
  const filtered = !!(search || kind || from || to);
  const reset = () => { setQ(''); setSearch(''); setKind(''); setFrom(''); setTo(''); setPage(1); };

  return (
    <div className="space-y-5">
      <PageHeader icon={FaExchangeAlt} eyebrow="Money" title="Transactions"
        description="Every wallet movement. Bets (sports and Aviator) are stakes, not withdrawals — only “Withdrawal (paid out)” is money sent to a player." />

      <form onSubmit={(e) => { e.preventDefault(); setSearch(q.trim()); setPage(1); }} className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[260px] flex-1">
          <BsSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={14} />
          <TextInput value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search player, email, #player id or reference" className="pl-9" aria-label="Search transactions" />
        </div>
        <select value={kind} onChange={(e) => { setKind(e.target.value); setPage(1); }} aria-label="Type" className={select}>
          {KIND_FILTERS.map((k) => <option key={k.id} value={k.id}>{k.label}</option>)}
        </select>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          From <input type="date" value={from} max={to || undefined} onChange={(e) => { setFrom(e.target.value); setPage(1); }} className={select} aria-label="From date" />
        </label>
        <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
          To <input type="date" value={to} min={from || undefined} onChange={(e) => { setTo(e.target.value); setPage(1); }} className={select} aria-label="To date" />
        </label>
        {filtered && <Btn type="button" onClick={reset}>Clear</Btn>}
      </form>

      {error && <Notice tone="red">{error}</Notice>}
      <div className="overflow-hidden rounded-2xl border border-border/70 bg-card">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-border px-4 py-2.5 text-xs text-muted-foreground">
          <span>{data ? `${data.count.toLocaleString()} transaction${data.count === 1 ? '' : 's'}${filtered ? ' match' : ''}` : 'Loading…'}</span>
          <label className="flex items-center gap-1.5">
            Show
            <select value={pageSize} onChange={(e) => { setPageSize(Number(e.target.value)); setPage(1); }} className="rounded-lg border border-border bg-background px-2 py-1" aria-label="Rows per page">
              {PAGE_SIZES.map((n) => <option key={n} value={n}>{n}</option>)}
            </select>
            per page · page {page} of {pages}
          </label>
        </div>
        {loading && !data ? <div className="h-48 animate-pulse bg-muted/40" /> : entries.length === 0 ? (
          <EmptyState icon={FaExchangeAlt} title={filtered ? 'No transactions match' : 'No transactions yet'}>
            {filtered ? 'Try a different search, type or date range.' : 'Wallet movements appear here as players deposit and play.'}
          </EmptyState>
        ) : (
          <div className={cx('overflow-x-auto', loading && 'opacity-60')}>
            <table className={tableClass}>
              <thead><tr>
                <th className={thClass}>Date</th><th className={thClass}>Player</th><th className={thClass}>Type</th>
                <th className={cx(thClass, 'text-right')}>Amount</th><th className={thClass}>Reference</th>
              </tr></thead>
              <tbody>
                {entries.map((e) => {
                  const n = Number(e.amount);
                  return (
                    <tr key={e.id} className={trClass}>
                      <td className={cx(tdClass, 'whitespace-nowrap text-xs text-muted-foreground')}>{new Date(e.created_at).toLocaleString()}</td>
                      <td className={tdClass}>
                        <Link href={`/players/${e.player_id}`} className="font-semibold hover:underline">{e.username ?? `#${e.player_id}`}</Link>
                        <span className="ml-1.5 font-mono text-[11px] text-muted-foreground">#{e.player_id}</span>
                      </td>
                      <td className={cx(tdClass, 'font-semibold', kindTone(e.kind))}>{kindLabel(e.kind)}</td>
                      <td className={cx(tdClass, 'text-right font-semibold tabular-nums', n < 0 ? 'text-foreground' : 'text-emerald-500')}>
                        {n > 0 ? '+' : n < 0 ? '−' : ''}${Math.abs(n).toFixed(2)}
                      </td>
                      <td className={cx(tdClass, 'max-w-[280px] truncate font-mono text-xs text-muted-foreground')} title={e.reference}>{e.reference || '—'}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
        {pages > 1 && (
          <div className="flex items-center justify-between border-t border-border px-4 py-3">
            <Btn size="sm" icon={BsChevronLeft} disabled={page <= 1 || loading} onClick={() => setPage((p) => p - 1)}>Previous</Btn>
            <span className="text-xs text-muted-foreground">
              {(page - 1) * pageSize + 1}–{Math.min(page * pageSize, data?.count ?? 0)} of {data?.count.toLocaleString()}
            </span>
            <Btn size="sm" disabled={page >= pages || loading} onClick={() => setPage((p) => p + 1)}>Next <BsChevronRight className="ml-1 inline" /></Btn>
          </div>
        )}
      </div>
    </div>
  );
}
