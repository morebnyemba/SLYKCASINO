'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { BsCalendar3, BsCashStack, BsCheckCircleFill, BsLink45Deg, BsPersonPlus, BsTicketPerforated, BsXCircleFill } from 'react-icons/bs';
import { Card, CardContent } from '@slyk/ui/components/card';
import { Spinner } from '@slyk/ui/components/spinner';
import { useAuth } from '@/lib/auth-context';
import { authedGet, useApi } from '@/lib/use-api';

interface Deposit { customer: string; amount: string; at: string }
interface Report {
  frame: string; label: string; start: string; end: string; oldest: string;
  deposits: { total: string; count: number; depositors: number; items: Deposit[]; page: number; more: boolean };
  tickets: { played: number; won: number; lost: number; open: number };
  clicks: number; signups: number; lost_stakes: string; losing_tickets: number; commission: string;
}

type Mode = 'today' | 'yesterday' | '7d' | '30d' | 'this_month' | 'last_month' | 'this_year' | 'day' | 'range';
const PRESETS: [Mode, string][] = [
  ['today', 'Today'], ['yesterday', 'Yesterday'], ['7d', '7 days'], ['30d', '30 days'],
  ['this_month', 'This month'], ['last_month', 'Last month'], ['this_year', 'This year'],
  ['day', 'Pick a day'], ['range', 'Date range'],
];

const money = (v: string | number) =>
  `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

function localISO(d: Date) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}

function Stat({ icon, label, value, sub, tone = '' }: { icon: React.ReactNode; label: string; value: string | number; sub?: string; tone?: string }) {
  return (
    <div className="rounded-xl border border-border bg-card p-3">
      <span className={`mb-1.5 block ${tone || 'text-secondary'}`}>{icon}</span>
      <p className={`text-xl font-extrabold tabular-nums ${tone}`}>{typeof value === 'number' ? value.toLocaleString() : value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
      {sub && <p className="text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  );
}

/** The agent's numbers for a chosen day or date range (up to ten years back): deposits, tickets, clicks, sign-ups. */
export function PeriodReport() {
  const { accessToken } = useAuth();
  const today = useMemo(() => localISO(new Date()), []);
  const tenYearsAgo = useMemo(() => { const d = new Date(); d.setFullYear(d.getFullYear() - 10); return localISO(d); }, []);
  const [mode, setMode] = useState<Mode>('today');
  const [day, setDay] = useState(today);
  const [from, setFrom] = useState(today);
  const [to, setTo] = useState(today);

  const query = useMemo(() => {
    if (mode === 'day') return day ? new URLSearchParams({ frame: 'custom', start: day, end: day }).toString() : null;
    if (mode === 'range') return from && to ? new URLSearchParams({ frame: 'custom', start: from, end: to }).toString() : null;
    return new URLSearchParams({ frame: mode }).toString();
  }, [mode, day, from, to]);
  const { data, error, loading } = useApi<Report>(query ? `/affiliates/me/report/?${query}` : null);

  // Older deposits ("Show more"), reset whenever the period changes.
  const [more, setMore] = useState<{ items: Deposit[]; page: number; more: boolean } | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);
  useEffect(() => { setMore(null); }, [query]);
  const hasMore = more ? more.more : !!data?.deposits.more;
  const loadMore = useCallback(async () => {
    if (!query || !accessToken || !data) return;
    setLoadingMore(true);
    const page = (more?.page ?? data.deposits.page) + 1;
    const res = await authedGet<Report>(`/affiliates/me/report/?${query}&page=${page}`, accessToken);
    setLoadingMore(false);
    if (res.data) {
      const next = res.data.deposits;
      setMore((m) => ({ items: [...(m?.items ?? []), ...next.items], page, more: next.more }));
    }
  }, [query, accessToken, data, more]);

  const deposits = [...(data?.deposits.items ?? []), ...(more?.items ?? [])];
  const t = data?.tickets;
  const dateInput = 'rounded-lg border border-border bg-input px-2.5 py-1.5 text-sm outline-none focus:ring-2 focus:ring-ring';

  return (
    <section className="space-y-3">
      <div className="flex items-center justify-between gap-2">
        <h2 className="flex items-center gap-2 text-sm font-bold"><BsCalendar3 size={13} /> {data?.label ?? 'Today'}</h2>
        <Link href="/account/affiliate/tickets" className="inline-flex items-center gap-1.5 rounded-lg bg-secondary px-3 py-1.5 text-xs font-bold text-secondary-foreground">
          <BsTicketPerforated size={13} /> View all tickets
        </Link>
      </div>

      <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1" role="tablist" aria-label="Period">
        {PRESETS.map(([id, label]) => (
          <button key={id} role="tab" aria-selected={mode === id} onClick={() => setMode(id)}
            className={`shrink-0 rounded-full border px-3 py-1.5 text-xs font-bold transition-colors ${mode === id ? 'border-secondary bg-secondary text-secondary-foreground' : 'border-border text-muted-foreground hover:text-foreground'}`}>
            {label}
          </button>
        ))}
      </div>
      {mode === 'day' && (
        <label className="flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">Day</span>
          <input type="date" value={day} min={tenYearsAgo} max={today} onChange={(e) => setDay(e.target.value)} className={dateInput} />
        </label>
      )}
      {mode === 'range' && (
        <div className="flex flex-wrap items-center gap-2 text-sm">
          <label className="flex items-center gap-2"><span className="text-muted-foreground">From</span>
            <input type="date" value={from} min={tenYearsAgo} max={to || today} onChange={(e) => setFrom(e.target.value)} className={dateInput} />
          </label>
          <label className="flex items-center gap-2"><span className="text-muted-foreground">To</span>
            <input type="date" value={to} min={from || tenYearsAgo} max={today} onChange={(e) => setTo(e.target.value)} className={dateInput} />
          </label>
          <span className="text-xs text-muted-foreground">Up to 10 years back.</span>
        </div>
      )}

      {error ? (
        <p className="text-sm text-destructive">{/400/.test(error) ? 'Pick dates within the last 10 years.' : 'Couldn’t load these numbers. Please try again.'}</p>
      ) : !data ? (
        <div className="flex justify-center py-6">{loading && <Spinner size={18} />}</div>
      ) : (
        <div className={`space-y-3 transition-opacity ${loading ? 'opacity-60' : ''}`}>
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            <Stat icon={<BsCashStack size={16} />} label="Deposits" value={money(data.deposits.total)}
              sub={`${data.deposits.count} deposit${data.deposits.count === 1 ? '' : 's'} · ${data.deposits.depositors} customer${data.deposits.depositors === 1 ? '' : 's'}`} tone="text-win" />
            <Stat icon={<BsTicketPerforated size={16} />} label="Tickets played" value={t?.played ?? 0} sub={t && t.open > 0 ? `${t.open} still running` : undefined} />
            <Stat icon={<BsCheckCircleFill size={16} />} label="Tickets won" value={t?.won ?? 0} tone="text-win" />
            <Stat icon={<BsXCircleFill size={16} />} label="Tickets lost" value={t?.lost ?? 0} tone="text-down" />
            <Stat icon={<BsCashStack size={16} />} label="Commission" value={money(data.commission)} sub={`on ${money(data.lost_stakes)} lost`} />
            <Stat icon={<BsLink45Deg size={16} />} label="Link clicks" value={data.clicks} />
            <Stat icon={<BsPersonPlus size={16} />} label="Sign-ups" value={data.signups} />
          </div>

          <Card className="rounded-2xl">
            <CardContent className="pt-4">
              <p className="mb-1 text-sm font-bold">Deposits <span className="font-normal text-muted-foreground">({data.deposits.count})</span></p>
              {deposits.length === 0 ? (
                <p className="py-3 text-sm text-muted-foreground">No deposits from your customers in this period.</p>
              ) : (
                <ul className="divide-y divide-border">
                  {deposits.map((d, i) => (
                    <li key={`${d.at}-${i}`} className="flex items-center justify-between gap-3 py-2.5">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold">{d.customer}</p>
                        <p className="text-xs text-muted-foreground">{new Date(d.at).toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' })}</p>
                      </div>
                      <p className="shrink-0 font-bold tabular-nums text-win">+{money(d.amount)}</p>
                    </li>
                  ))}
                </ul>
              )}
              {hasMore && (
                <div className="mt-2 flex justify-center">
                  <button onClick={() => void loadMore()} disabled={loadingMore}
                    className="flex items-center gap-2 rounded-lg border border-border px-4 py-2 text-sm font-bold hover:bg-muted disabled:opacity-60">
                    {loadingMore && <Spinner size={13} />} Show more deposits
                  </button>
                </div>
              )}
            </CardContent>
          </Card>
        </div>
      )}
    </section>
  );
}
