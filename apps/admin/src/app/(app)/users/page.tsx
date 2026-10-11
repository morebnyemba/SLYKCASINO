'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { BsChevronLeft, BsChevronRight, BsSearch } from 'react-icons/bs';
import { FaUsers } from 'react-icons/fa';
import {
  Badge, Btn, EmptyState, Notice, PageHeader, TextInput, cx, money, tableClass, tdClass, thClass, trClass,
} from '@/components/console/ui';
import { useApi } from '@/lib/use-api';

interface Player {
  id: number; username: string; email: string; full_name?: string; kyc_status: string;
  balance: string; currency: string; created_at: string; is_suspended: boolean;
}
interface PlayersResponse { count: number; next: string | null; previous: string | null; results: Player[] }

const PAGE_SIZE = 50;
const KYC_TONE: Record<string, 'green' | 'gold' | 'red' | 'slate'> = {
  verified: 'green', pending: 'gold', rejected: 'red', none: 'slate', unverified: 'slate',
};
const select = 'h-10 rounded-xl border border-border bg-background px-3 text-sm';

/** Every registered player, newest first: search by username, email, name or #id. */
export default function PlayersPage() {
  const [q, setQ] = useState('');
  const [search, setSearch] = useState('');
  const [kyc, setKyc] = useState('');
  const [status, setStatus] = useState('');
  const [page, setPage] = useState(1);
  const params = new URLSearchParams({
    page: String(page), page_size: String(PAGE_SIZE),
    ...(search && { q: search }), ...(kyc && { kyc }), ...(status && { status }),
  });
  const { data, loading, error } = useApi<PlayersResponse>(`/players/?${params}`);
  const players = data?.results ?? [];
  const pages = data ? Math.max(1, Math.ceil(data.count / PAGE_SIZE)) : 1;

  // Set after a permanent deletion (read on mount to avoid a Suspense boundary for useSearchParams).
  const [deleted, setDeleted] = useState<string | null>(null);
  useEffect(() => {
    const name = new URLSearchParams(window.location.search).get('deleted');
    if (name) { setDeleted(name); window.history.replaceState(null, '', window.location.pathname); }
  }, []);

  // Search as the operator types (after a short pause).
  useEffect(() => {
    const t = window.setTimeout(() => { setSearch(q.trim()); setPage(1); }, 350);
    return () => window.clearTimeout(t);
  }, [q]);

  return (
    <div className="space-y-5">
      <PageHeader icon={FaUsers} eyebrow="Players" title="Players"
        description="Every registered player, newest first. Open a player for their balance, tickets, Aviator bets, withdrawals and KYC." />
      {deleted && <Notice tone="green" onClose={() => setDeleted(null)}>Player {deleted} and all their data were permanently deleted.</Notice>}

      <form onSubmit={(e) => { e.preventDefault(); setSearch(q.trim()); setPage(1); }} className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[260px] flex-1">
          <BsSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={14} />
          <TextInput value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search username, email, name or #id" className="pl-9" aria-label="Search players" />
        </div>
        <select value={kyc} onChange={(e) => { setKyc(e.target.value); setPage(1); }} aria-label="KYC" className={select}>
          <option value="">Any KYC</option><option value="verified">Verified</option><option value="pending">Pending review</option>
          <option value="unverified">Unverified</option>
        </select>
        <select value={status} onChange={(e) => { setStatus(e.target.value); setPage(1); }} aria-label="Status" className={select}>
          <option value="">Active & suspended</option><option value="active">Active</option><option value="suspended">Suspended</option>
        </select>
        {(search || kyc || status) && <Btn type="button" onClick={() => { setQ(''); setSearch(''); setKyc(''); setStatus(''); setPage(1); }}>Clear</Btn>}
      </form>

      {error && <Notice tone="red">{error}</Notice>}
      <div className="overflow-hidden rounded-2xl border border-border/70 bg-card">
        <div className="flex items-center justify-between border-b border-border px-4 py-2.5 text-xs text-muted-foreground">
          <span>{data ? `${data.count.toLocaleString()} player${data.count === 1 ? '' : 's'}${search ? ` matching “${search}”` : ''}` : 'Loading…'}</span>
          <span>Page {page} of {pages}</span>
        </div>
        {loading && !data ? <div className="h-48 animate-pulse bg-muted/40" /> : players.length === 0 ? (
          <EmptyState icon={FaUsers} title={search || kyc || status ? 'No players match' : 'No players yet'}>
            {search ? 'Try part of the username or email, or #id.' : 'Players appear here as they register.'}
          </EmptyState>
        ) : (
          <div className={cx('overflow-x-auto', loading && 'opacity-60')}>
            <table className={tableClass}>
              <thead><tr>
                <th className={thClass}>#</th><th className={thClass}>Player</th><th className={thClass}>KYC</th>
                <th className={thClass}>Balance</th><th className={thClass}>Status</th><th className={thClass}>Joined</th><th className={thClass} />
              </tr></thead>
              <tbody>
                {players.map((p) => (
                  <tr key={p.id} className={trClass}>
                    <td className={cx(tdClass, 'font-mono text-xs text-muted-foreground')}>{p.id}</td>
                    <td className={tdClass}>
                      <Link href={`/players/${p.id}`} className="font-semibold hover:underline">{p.username}</Link>
                      <p className="text-xs text-muted-foreground">{p.email}{p.full_name ? ` · ${p.full_name}` : ''}</p>
                    </td>
                    <td className={tdClass}><Badge tone={KYC_TONE[p.kyc_status] ?? 'slate'}>{p.kyc_status || 'none'}</Badge></td>
                    <td className={cx(tdClass, 'font-semibold tabular-nums')}>{money(p.balance)}</td>
                    <td className={tdClass}>{p.is_suspended ? <Badge tone="red" dot>Suspended</Badge> : <Badge tone="green" dot>Active</Badge>}</td>
                    <td className={cx(tdClass, 'whitespace-nowrap text-xs text-muted-foreground')}>{new Date(p.created_at).toLocaleDateString()}</td>
                    <td className={cx(tdClass, 'text-right')}>
                      <Link href={`/players/${p.id}`} className="rounded-lg border border-border px-2.5 py-1 text-xs font-semibold hover:bg-muted">View</Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        {pages > 1 && (
          <div className="flex items-center justify-between border-t border-border px-4 py-3">
            <Btn size="sm" icon={BsChevronLeft} disabled={page <= 1 || loading} onClick={() => setPage((n) => n - 1)}>Previous</Btn>
            <span className="text-xs text-muted-foreground">{(page - 1) * PAGE_SIZE + 1}–{Math.min(page * PAGE_SIZE, data?.count ?? 0)} of {data?.count}</span>
            <Btn size="sm" disabled={page >= pages || loading} onClick={() => setPage((n) => n + 1)}>Next <BsChevronRight className="ml-1 inline" /></Btn>
          </div>
        )}
      </div>
    </div>
  );
}
