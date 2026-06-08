'use client';

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

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error) return <p className="text-sm text-destructive">{error}</p>;

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">My Bets</h1>
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
