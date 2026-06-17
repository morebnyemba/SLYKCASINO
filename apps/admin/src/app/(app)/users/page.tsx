'use client';

import { Card } from '@slyk/ui/components/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@slyk/ui/components/table';
import { Badge } from '@slyk/ui/components/badge';
import { useApi } from '@/lib/use-api';

interface Player {
  id: string | number;
  username: string;
  email: string;
  kyc_status: string;
  balance: number | string;
  currency: string;
  created_at: string;
}

interface PlayersResponse {
  results?: Player[];
}

export default function UsersPage() {
  const { data, loading, error } = useApi<PlayersResponse>('/players/');
  const players = data?.results ?? [];

  return (
    <div>
      <h1 className="text-2xl font-bold">Players</h1>
      <p className="mb-4 text-muted-foreground">Operator view of registered players. Raw edits go through the Django admin.</p>
      {error && <p className="mb-3 text-sm text-destructive">{error}</p>}
      <Card className="p-2">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Username</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>KYC</TableHead>
              <TableHead>Balance</TableHead>
              <TableHead>Joined</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading && (
              <TableRow><TableCell colSpan={5} className="text-muted-foreground">Loading…</TableCell></TableRow>
            )}
            {!loading && players.length === 0 && (
              <TableRow><TableCell colSpan={5} className="text-muted-foreground">No players yet.</TableCell></TableRow>
            )}
            {players.map((p) => (
              <TableRow key={p.id}>
                <TableCell className="font-medium">{p.username}</TableCell>
                <TableCell>{p.email}</TableCell>
                <TableCell><Badge variant="outline">{p.kyc_status}</Badge></TableCell>
                <TableCell>{p.balance} {p.currency}</TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {new Date(p.created_at).toLocaleDateString()}
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
