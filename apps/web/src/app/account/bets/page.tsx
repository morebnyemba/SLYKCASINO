'use client';

import { useMemo, useState } from 'react';
import { FaDownload, FaCoins, FaTrophy, FaPercentage } from 'react-icons/fa';
import { Card } from '@slyk/ui/components/card';
import {
  BetTicket, isSettled, money, sortTickets, ticketFromBet, ticketFromSlip, type ApiBet, type ApiSlip,
} from '@/components/bet-ticket';
import { useApi } from '@/lib/use-api';

type Tab = 'all' | 'open' | 'settled';

const TABS: { key: Tab; label: string }[] = [
  { key: 'all', label: 'All' },
  { key: 'open', label: 'Open' },
  { key: 'settled', label: 'Settled' },
];

export default function MyBetsPage() {
  const { data, loading, error } = useApi<{ results?: ApiBet[] }>('/bets/', { allPages: true });
  const { data: slipsData, loading: slipsLoading, error: slipsError } = useApi<{ results?: ApiSlip[] }>('/betslips/', { allPages: true });
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [tab, setTab] = useState<Tab>('all');

  const all = useMemo(
    () => sortTickets([...(data?.results ?? []).map(ticketFromBet), ...(slipsData?.results ?? []).map(ticketFromSlip)]),
    [data, slipsData],
  );
  const inRange = all.filter((t) => {
    // Local calendar date, matching the date inputs and the ticket header.
    const p = new Date(t.placedAt);
    const d = `${p.getFullYear()}-${String(p.getMonth() + 1).padStart(2, '0')}-${String(p.getDate()).padStart(2, '0')}`;
    if (fromDate && d < fromDate) return false;
    if (toDate && d > toDate) return false;
    return true;
  });
  const tickets = inRange.filter((t) => tab === 'all' || (tab === 'settled') === isSettled(t.status));
  const openCount = inRange.filter((t) => !isSettled(t.status)).length;

  const stats = useMemo(() => {
    const totalStaked = inRange.reduce((sum, t) => sum + t.stake, 0);
    const decided = inRange.filter((t) => t.status === 'won' || t.status === 'lost');
    const won = inRange.filter((t) => t.status === 'won');
    const totalPayout = won.reduce((sum, t) => sum + (t.payout ?? 0), 0);
    const winRate = decided.length > 0 ? (won.length / decided.length) * 100 : 0;
    return { totalStaked, totalPayout, winRate };
  }, [inRange]);

  function exportCsv() {
    const esc = (v: string | number) => `"${String(v).replace(/"/g, '""')}"`;
    const header = 'Ticket,Type,Selections,Stake,Odds,Payout,Status,Placed\n';
    const rows = inRange.map((t) =>
      [
        `${t.kind === 'single' ? 'S' : 'M'}${t.id}`, t.kind,
        t.legs.map((l) => `${l.match} - ${l.pick} @ ${l.odds.toFixed(2)}`).join(' | '),
        t.stake.toFixed(2), t.odds.toFixed(2), t.payout?.toFixed(2) ?? '', t.status, t.placedAt,
      ].map(esc).join(','),
    );
    const blob = new Blob([header + rows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'my-bets.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  if (loading || slipsLoading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error || slipsError) return <p className="text-sm text-destructive">{error || slipsError}</p>;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">My Bets</h1>
        <div className="flex flex-wrap items-center gap-2">
          <input
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
            aria-label="From date"
            className="rounded-md border border-border bg-background px-2 py-1 text-xs"
          />
          <span className="text-xs text-muted-foreground">to</span>
          <input
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
            aria-label="To date"
            className="rounded-md border border-border bg-background px-2 py-1 text-xs"
          />
          {all.length > 0 && (
            <button
              onClick={exportCsv}
              className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent/10"
            >
              <FaDownload size={11} />
              Export CSV
            </button>
          )}
        </div>
      </div>

      {inRange.length > 0 && (
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          <Card className="rounded-xl border-gold/10 p-4">
            <FaCoins className="mb-2 text-secondary" size={16} />
            <p className="text-xs text-muted-foreground">Total staked</p>
            <p className="text-lg font-bold">{money(stats.totalStaked)}</p>
          </Card>
          <Card className="rounded-xl border-gold/10 p-4">
            <FaTrophy className="mb-2 text-gold" size={16} />
            <p className="text-xs text-muted-foreground">Total returns</p>
            <p className="text-lg font-bold text-win">{money(stats.totalPayout)}</p>
          </Card>
          <Card className="rounded-xl border-gold/10 p-4">
            <FaPercentage className="mb-2 text-secondary" size={16} />
            <p className="text-xs text-muted-foreground">Win rate</p>
            <p className="text-lg font-bold">{stats.winRate.toFixed(0)}%</p>
          </Card>
        </div>
      )}

      <div className="mb-3 inline-flex rounded-lg border border-border bg-card p-0.5" role="tablist">
        {TABS.map(({ key, label }) => (
          <button
            key={key}
            role="tab"
            aria-selected={tab === key}
            onClick={() => setTab(key)}
            className={`rounded-md px-3 py-1.5 text-xs font-bold transition-colors ${
              tab === key ? 'bg-secondary text-white' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {label}
            {key === 'open' && openCount > 0 && <span className="ml-1 opacity-80">({openCount})</span>}
          </button>
        ))}
      </div>

      {tickets.length === 0 ? (
        <Card className="rounded-xl border-gold/10 p-6 text-center text-sm text-muted-foreground">
          {all.length === 0
            ? 'No bets yet. Bets you place will show up here as tickets.'
            : inRange.length === 0 ? 'No bets in this date range.' : `No ${tab} bets.`}
        </Card>
      ) : (
        <div className="grid items-start gap-3 md:grid-cols-2">
          {tickets.map((t) => <BetTicket key={t.key} ticket={t} />)}
        </div>
      )}
    </div>
  );
}
