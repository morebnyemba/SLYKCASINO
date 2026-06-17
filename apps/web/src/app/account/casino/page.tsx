'use client';

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
  const rounds = data?.results ?? [];

  if (loading) return <p className="text-sm text-muted-foreground">Loading…</p>;
  if (error) return <p className="text-sm text-destructive">{error}</p>;

  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">Casino History</h1>
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
                <TableCell colSpan={6} className="text-muted-foreground">No casino rounds yet. Try a game!</TableCell>
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
