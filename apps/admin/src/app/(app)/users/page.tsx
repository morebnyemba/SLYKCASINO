'use client';

import Link from 'next/link';
import { FaUsers } from 'react-icons/fa';
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
  is_suspended: boolean;
}

interface PlayersResponse {
  results?: Player[];
}

export default function UsersPage() {
  const { data, loading, error } = useApi<PlayersResponse>('/players/');
  const players = data?.results ?? [];

  return (
    <div>
      <div className="mb-1 flex items-center gap-2.5">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gold/15 text-gold">
          <FaUsers size={13} />
        </span>
        <h1 className="text-2xl font-bold">Players</h1>
      </div>
      <p className="mb-4 text-muted-foreground">Operator view of registered players.</p>
      {error && <p className="mb-3 text-sm text-destructive">{error}</p>}
      <Card className="rounded-2xl border-gold/15 p-2">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Username</TableHead>
              <TableHead>Email</TableHead>
              <TableHead>KYC</TableHead>
              <TableHead>Balance</TableHead>
              <TableHead>Status</TableHead>
              <TableHead>Joined</TableHead>
              <TableHead></TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {loading && (
              <TableRow><TableCell colSpan={7} className="text-muted-foreground">Loading…</TableCell></TableRow>
            )}
            {!loading && players.length === 0 && (
              <TableRow><TableCell colSpan={7} className="text-muted-foreground">No players yet.</TableCell></TableRow>
            )}
            {players.map((p) => (
              <TableRow key={p.id}>
                <TableCell className="font-medium">{p.username}</TableCell>
                <TableCell>{p.email}</TableCell>
                <TableCell><Badge variant="outline">{p.kyc_status}</Badge></TableCell>
                <TableCell>{p.balance} {p.currency}</TableCell>
                <TableCell>
                  {p.is_suspended ? <Badge variant="destructive">Suspended</Badge> : <Badge variant="success">Active</Badge>}
                </TableCell>
                <TableCell className="text-xs text-muted-foreground">
                  {new Date(p.created_at).toLocaleDateString()}
                </TableCell>
                <TableCell>
                  <Link href={`/players/${p.id}`} className="rounded px-2 py-1 text-xs border border-border hover:bg-accent">
                    View
                  </Link>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Card>
    </div>
  );
}
