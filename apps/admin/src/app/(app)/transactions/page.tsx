'use client';

import { useState } from 'react';
import Link from 'next/link';
import { FaExchangeAlt } from 'react-icons/fa';
import { Card, CardContent } from '@slyk/ui/components/card';
import { useApi } from '@/lib/use-api';

interface LedgerEntry {
  id: number;
  amount: string;
  kind: string;
  reference: string;
  idempotency_key: string;
  created_at: string;
  player_id: number;
}

interface LedgerResponse {
  count: number;
  next: string | null;
  previous: string | null;
  results?: LedgerEntry[];
}

const PAGE_SIZE = 25;

export default function TransactionsPage() {
  const [playerId, setPlayerId] = useState('');
  const [page, setPage] = useState(1);

  const query = playerId ? `&player_id=${playerId}` : '';
  const { data, loading, error } = useApi<LedgerResponse>(`/admin/ledger/?page=${page}${query}`);
  const entries = data?.results ?? [];
  const totalPages = data?.count ? Math.ceil(data.count / PAGE_SIZE) : 1;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2.5">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gold/15 text-gold">
          <FaExchangeAlt size={13} />
        </span>
        <h1 className="text-2xl font-bold">Transactions</h1>
      </div>

      <div className="flex items-center gap-2">
        <input
          type="text"
          value={playerId}
          onChange={(e) => { setPlayerId(e.target.value); setPage(1); }}
          placeholder="Filter by player ID"
          className="w-48 rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        />
      </div>

      {error && <p className="text-sm text-destructive">{error}</p>}

      <Card>
        <CardContent className="p-0">
          {loading && <p className="p-4 text-sm text-muted-foreground">Loading transactions…</p>}
          {!loading && entries.length === 0 && (
            <p className="p-4 text-sm text-muted-foreground">No ledger entries.</p>
          )}
          {entries.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Player</th>
                  <th className="px-4 py-3 font-medium">Kind</th>
                  <th className="px-4 py-3 font-medium">Amount</th>
                  <th className="px-4 py-3 font-medium">Reference</th>
                  <th className="px-4 py-3 font-medium">Date</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-3">
                      <Link href={`/players/${e.player_id}`} className="text-gold hover:underline">#{e.player_id}</Link>
                    </td>
                    <td className="px-4 py-3">{e.kind}</td>
                    <td className={`px-4 py-3 font-medium ${Number(e.amount) < 0 ? 'text-destructive' : 'text-emerald-600'}`}>
                      {e.amount}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{e.reference}</td>
                    <td className="px-4 py-3 text-muted-foreground">{new Date(e.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      {totalPages > 1 && (
        <div className="flex items-center justify-between text-sm">
          <button
            onClick={() => setPage((p) => Math.max(1, p - 1))}
            disabled={page <= 1}
            className="rounded-md border border-border px-3 py-1.5 hover:bg-accent disabled:opacity-50"
          >
            Previous
          </button>
          <span className="text-muted-foreground">Page {page} of {totalPages}</span>
          <button
            onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
            disabled={page >= totalPages}
            className="rounded-md border border-border px-3 py-1.5 hover:bg-accent disabled:opacity-50"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
