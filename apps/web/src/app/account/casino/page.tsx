'use client';

import { useState } from 'react';
import { FaDownload } from 'react-icons/fa';
import { Card } from '@slyk/ui/components/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@slyk/ui/components/table';
import { Badge } from '@slyk/ui/components/badge';
import { useApi } from '@/lib/use-api';

interface Round {
  id: number;
  game: number;
  stake: string;
  win: string;
  status: string;
  created_at: string;
}

interface RoundsResponse { results?: Round[] }

export default function CasinoHistoryPage() {
  const { data, loading, error } = useApi<RoundsResponse>('/casino/rounds/');
  const allRounds = data?.results ?? [];
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const rounds = allRounds.filter((r) => {
    const d = r.created_at.slice(0, 10);
    if (fromDate && d < fromDate) return false;
    if (toDate && d > toDate) return false;
    return true;
  });

  function exportCsv() {
    const header = 'Round,Stake,Win,Net,Status,Date\n';
    const rows = rounds.map((r) => {
      const net = (parseFloat(r.win) - parseFloat(r.stake)).toFixed(2);
      return [r.id, r.stake, r.win, net, r.status, r.created_at].join(',');
    });
    const blob = new Blob([header + rows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'casino-history.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error) return <p className="text-sm text-destructive">{error}</p>;

  return (
    <div>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">Casino History</h1>
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
          {allRounds.length > 0 && (
            <button
              onClick={exportCsv}
              className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent"
            >
              <FaDownload size={11} />
              Export CSV
            </button>
          )}
        </div>
      </div>
      <Card className="p-2">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Round</TableHead>
              <TableHead>Stake</TableHead>
              <TableHead>Win</TableHead>
              <TableHead>Net</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Date</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rounds.length === 0 && (
              <TableRow>
                <TableCell colSpan={6} className="text-muted-foreground">
                  {allRounds.length === 0 ? 'No casino rounds yet. Try a game!' : 'No rounds in this date range.'}
                </TableCell>
              </TableRow>
            )}
            {rounds.map((r) => {
              const net = parseFloat(r.win) - parseFloat(r.stake);
              return (
                <TableRow key={r.id}>
                  <TableCell className="text-xs text-muted-foreground">#{r.id}</TableCell>
                  <TableCell>{r.stake}</TableCell>
                  <TableCell>{r.win}</TableCell>
                  <TableCell className={net >= 0 ? 'text-green-600 font-medium' : 'text-red-500'}>
                    {net >= 0 ? '+' : ''}{net.toFixed(2)}
                  </TableCell>
                  <TableCell>
                    <Badge variant={r.status === 'settled' ? 'default' : 'secondary'}>{r.status}</Badge>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {new Date(r.created_at).toLocaleDateString()}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
