'use client';

import { useMemo, useState } from 'react';
import { FaDownload } from 'react-icons/fa';
import { Card } from '@slyk/ui/components/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@slyk/ui/components/table';
import { Badge } from '@slyk/ui/components/badge';
import { useApi } from '@/lib/use-api';

interface Bet {
  id: string | number;
  event: string | number;
  stake: string;
  odds: string;
  status: string;
  payout: string | null;
  placed_at: string;
}

interface BetsResponse {
  results?: Bet[];
}

interface SlipLeg {
  id: number;
  event: string;
  selection: string;
  odds: string;
  result: string;
}

interface BetSlip {
  id: number;
  stake: string;
  combined_odds: string;
  status: string;
  payout: string | null;
  placed_at: string;
  legs: SlipLeg[];
}

interface SlipsResponse {
  results?: BetSlip[];
}

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive'> = {
  open: 'default',
  won: 'default',
  lost: 'destructive',
  void: 'secondary',
  pending: 'secondary',
};

export default function MyBetsPage() {
  const { data, loading, error } = useApi<BetsResponse>('/bets/');
  const { data: slipsData } = useApi<SlipsResponse>('/betslips/');
  const slips = slipsData?.results ?? [];
  const allBets = data?.results ?? [];
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const bets = allBets.filter((b) => {
    const d = b.placed_at.slice(0, 10);
    if (fromDate && d < fromDate) return false;
    if (toDate && d > toDate) return false;
    return true;
  });

  const stats = useMemo(() => {
    const totalStaked = bets.reduce((sum, b) => sum + parseFloat(b.stake || '0'), 0);
    const settled = bets.filter((b) => b.status === 'won' || b.status === 'lost');
    const won = bets.filter((b) => b.status === 'won');
    const totalPayout = won.reduce((sum, b) => sum + parseFloat(b.payout || '0'), 0);
    const winRate = settled.length > 0 ? (won.length / settled.length) * 100 : 0;
    return { totalStaked, totalPayout, winRate, count: bets.length };
  }, [bets]);

  function exportCsv() {
    const header = 'Event,Stake,Odds,Payout,Status,Date\n';
    const rows = bets.map((b) =>
      [b.event, b.stake, b.odds, b.payout ?? '', b.status, b.placed_at].join(','),
    );
    const blob = new Blob([header + rows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'my-bets.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error) return <p className="text-sm text-destructive">{error}</p>;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">My Bets</h1>
        <div className="flex items-center gap-2">
          <input
            type="date"
            value={fromDate}
            onChange={(e) => setFromDate(e.target.value)}
            className="rounded-md border border-border bg-background px-2 py-1 text-xs"
          />
          <span className="text-xs text-muted-foreground">to</span>
          <input
            type="date"
            value={toDate}
            onChange={(e) => setToDate(e.target.value)}
            className="rounded-md border border-border bg-background px-2 py-1 text-xs"
          />
          {allBets.length > 0 && (
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

      {bets.length > 0 && (
        <div className="mb-4 grid gap-3 sm:grid-cols-3">
          <Card className="p-4">
            <p className="text-xs text-muted-foreground">Total staked</p>
            <p className="text-lg font-bold">{stats.totalStaked.toFixed(2)}</p>
          </Card>
          <Card className="p-4">
            <p className="text-xs text-muted-foreground">Total returns</p>
            <p className="text-lg font-bold text-green-600">{stats.totalPayout.toFixed(2)}</p>
          </Card>
          <Card className="p-4">
            <p className="text-xs text-muted-foreground">Win rate</p>
            <p className="text-lg font-bold">{stats.winRate.toFixed(0)}%</p>
          </Card>
        </div>
      )}

      <Card className="p-2">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Event</TableHead>
              <TableHead>Stake</TableHead>
              <TableHead>Odds</TableHead>
              <TableHead>Payout</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Date</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {bets.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-muted-foreground">
                  {allBets.length === 0 ? 'No bets yet.' : 'No bets in this date range.'}
                </TableCell>
              </TableRow>
            )}
            {bets.map((b) => (
              <TableRow key={b.id}>
                <TableCell>{b.event}</TableCell>
                <TableCell>{b.stake}</TableCell>
                <TableCell>{b.odds}</TableCell>
                <TableCell>{b.payout ?? '—'}</TableCell>
                <TableCell>
                  <Badge variant={STATUS_VARIANT[b.status] ?? 'secondary'}>{b.status}</Badge>
                </TableCell>
                <TableCell className="text-muted-foreground text-xs">
                  {new Date(b.placed_at).toLocaleDateString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>

      {slips.length > 0 && (
        <div className="mt-8">
          <h2 className="mb-3 text-lg font-bold">Accumulators</h2>
          <div className="grid gap-3 sm:grid-cols-2">
            {slips.map((s) => (
              <Card key={s.id} className="p-4">
                <div className="mb-2 flex items-center justify-between">
                  <span className="text-sm font-semibold">{s.legs.length}-leg accumulator</span>
                  <Badge variant={STATUS_VARIANT[s.status] ?? 'secondary'}>{s.status}</Badge>
                </div>
                <ul className="mb-3 space-y-1 border-l-2 border-border pl-3 text-xs">
                  {s.legs.map((leg) => (
                    <li key={leg.id} className="flex items-center justify-between gap-2">
                      <span className="truncate text-muted-foreground">{leg.event}</span>
                      <span className="font-mono shrink-0">{leg.odds}</span>
                    </li>
                  ))}
                </ul>
                <div className="flex items-center justify-between border-t border-border pt-2 text-xs">
                  <span className="text-muted-foreground">Stake {s.stake} @ {s.combined_odds}</span>
                  <span className="font-semibold">
                    {s.status === 'won' ? <span className="text-green-600">+{s.payout}</span> : `Return ${(parseFloat(s.stake) * parseFloat(s.combined_odds)).toFixed(2)}`}
                  </span>
                </div>
              </Card>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
