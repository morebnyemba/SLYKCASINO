'use client';

import { useMemo } from 'react';
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

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive'> = {
  open: 'default',
  won: 'default',
  lost: 'destructive',
  void: 'secondary',
  pending: 'secondary',
};

export default function MyBetsPage() {
  const { data, loading, error } = useApi<BetsResponse>('/bets/');
  const bets = data?.results ?? [];

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
      <div className="mb-4 flex items-center justify-between">
        <h1 className="text-2xl font-bold">My Bets</h1>
        {bets.length > 0 && (
          <button
            onClick={exportCsv}
            className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent"
          >
            <FaDownload size={11} />
            Export CSV
          </button>
        )}
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
                <TableCell colSpan={6} className="text-muted-foreground">No bets yet.</TableCell>
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
    </div>
  );
}
