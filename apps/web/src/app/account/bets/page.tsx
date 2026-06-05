import type { Metadata } from 'next';
import { Card } from '@slyk/ui/components/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@slyk/ui/components/table';
import { Badge } from '@slyk/ui/components/badge';
import { apiGet } from '@/lib/config';

export const metadata: Metadata = { title: 'My Bets — SLYK' };

interface Bet {
  id: string | number;
  event: string;
  stake: number;
  odds: number;
  status: string;
}

export default async function MyBetsPage() {
  const data = await apiGet<Bet>('/bets/');
  const bets = (data.results ?? []) as Bet[];
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
              <TableHead>Status</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {bets.length === 0 && (
              <TableRow><TableCell colSpan={4} className="text-muted-foreground">No bets yet.</TableCell></TableRow>
            )}
            {bets.map((b) => (
              <TableRow key={b.id}>
                <TableCell>{b.event}</TableCell>
                <TableCell>{b.stake}</TableCell>
                <TableCell>{b.odds}</TableCell>
                <TableCell><Badge variant="secondary">{b.status}</Badge></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
