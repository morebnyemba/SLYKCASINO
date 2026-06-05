import type { Metadata } from 'next';
import { Card } from '@slyk/ui/components/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@slyk/ui/components/table';
import { Badge } from '@slyk/ui/components/badge';
import { apiGet } from '@/lib/config';

export const metadata: Metadata = { title: 'Players — SLYK Admin' };

interface Player {
  id: string | number;
  username: string;
  email: string;
  kyc_status: string;
  balance: number | string;
}

export default async function UsersPage() {
  const data = await apiGet<Player>('/players/');
  const players = (data.results ?? []) as Player[];
  return (
    <div>
      <h1 className="text-2xl font-bold">Players</h1>
      <p className="mb-4 text-muted-foreground">Operator view of registered players. Raw edits go through the Django admin.</p>
      <Card className="p-2">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Username</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>KYC</TableHead>
              <TableHead>Balance</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {players.length === 0 && (
              <TableRow><TableCell colSpan={4} className="text-muted-foreground">No players yet.</TableCell></TableRow>
            )}
            {players.map((p) => (
              <TableRow key={p.id}>
                <TableCell>{p.username}</TableCell>
                <TableCell>{p.email}</TableCell>
                <TableCell><Badge variant="outline">{p.kyc_status}</Badge></TableCell>
                <TableCell>{p.balance}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
