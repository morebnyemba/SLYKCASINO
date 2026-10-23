'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { BsArrowLeft } from 'react-icons/bs';
import { BetTicket, ticketFromRow, type ApiBet, type ApiSlip } from '@/components/bet-ticket';
import { useAuth } from '@/lib/auth-context';
import { authedGet, useApi } from '@/lib/use-api';
import { LoadingState, Spinner } from '@slyk/ui/components/spinner';

type Row = (ApiBet | ApiSlip) & { kind: 'single' | 'multiple'; ticket: string; customer: string };
type Status = '' | 'open' | 'won' | 'lost' | 'void';
interface Page { results: Row[]; next_cursor: string | null; counts: Record<Exclude<Status, ''>, number> }

const PAGE = 30;
const TABS: [Status, string][] = [['', 'All'], ['open', 'Running'], ['won', 'Won'], ['lost', 'Lost'], ['void', 'Void']];

/** Every ticket the agent's customers have placed, newest first. */
export default function AgentTicketsPage() {
  const { accessToken } = useAuth();
  const [status, setStatus] = useState<Status>('');
  const query = useMemo(() => new URLSearchParams({ limit: String(PAGE), ...(status ? { status } : {}) }).toString(), [status]);
  const first = useApi<Page>(`/affiliates/me/tickets/?${query}`);

  const [extra, setExtra] = useState<{ rows: Row[]; cursor: string | null } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  useEffect(() => { setExtra(null); }, [query]);
  const cursor = extra ? extra.cursor : first.data?.next_cursor ?? null;
  const loadMore = useCallback(async () => {
    if (!cursor || !accessToken) return;
    setLoadingMore(true);
    const res = await authedGet<Page>(`/affiliates/me/tickets/?${query}&cursor=${encodeURIComponent(cursor)}`, accessToken);
    setLoadingMore(false);
    if (res.data) {
      const page = res.data;
      setExtra((e) => ({ rows: [...(e?.rows ?? []), ...page.results], cursor: page.next_cursor }));
    }
  }, [cursor, accessToken, query]);

  const rows = useMemo(() => {
    const seen = new Set<string>();
    return [...(first.data?.results ?? []), ...(extra?.rows ?? [])]
      .filter((r) => (seen.has(r.ticket) ? false : (seen.add(r.ticket), true)));
  }, [first.data, extra]);
  const counts = first.data?.counts;
  const total = counts ? Object.values(counts).reduce((a, b) => a + b, 0) : undefined;

  return (
    <div className="space-y-4">
      <Link href="/account/affiliate" className="inline-flex items-center gap-1.5 text-sm font-semibold text-muted-foreground hover:text-foreground">
        <BsArrowLeft size={13} /> Agent dashboard
      </Link>
      <h1 className="text-2xl font-bold">My customers’ tickets</h1>

      <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1" role="tablist">
        {TABS.map(([id, label]) => {
          const n = id ? counts?.[id] : total;
          return (
            <button key={id || 'all'} role="tab" aria-selected={status === id} onClick={() => setStatus(id)}
              className={`shrink-0 rounded-full border px-3.5 py-1.5 text-sm font-bold transition-colors ${status === id ? 'border-secondary bg-secondary text-secondary-foreground' : 'border-border text-muted-foreground hover:text-foreground'}`}>
              {label}{n != null && <span className="ml-1.5 opacity-70">{n}</span>}
            </button>
          );
        })}
      </div>

      {first.loading && !first.data ? (
        <LoadingState />
      ) : first.error ? (
        <p className="text-sm text-destructive">Couldn’t load tickets. <button onClick={first.refetch} className="underline">Retry</button></p>
      ) : rows.length === 0 ? (
        <p className="rounded-2xl border border-border bg-card px-5 py-8 text-center text-sm text-muted-foreground">
          No tickets here yet. They show up as soon as your customers bet.
        </p>
      ) : (
        <>
          <div className="grid items-start gap-2.5 md:grid-cols-2">
            {rows.map((r) => (
              <div key={r.ticket} className="space-y-1">
                <p className="px-1 text-xs font-semibold text-muted-foreground">{r.customer}</p>
                <BetTicket ticket={ticketFromRow(r)} isPublic collapsible />
              </div>
            ))}
          </div>
          {cursor && (
            <div className="flex justify-center">
              <button onClick={() => void loadMore()} disabled={loadingMore}
                className="flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-bold hover:bg-muted disabled:opacity-60">
                {loadingMore && <Spinner size={13} />} Show older tickets
              </button>
            </div>
          )}
        </>
      )}
    </div>
  );
}
