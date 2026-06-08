'use client';

import { useState } from 'react';
import { RealtimeFeed } from '@/components/realtime-feed';
import { Card } from '@slyk/ui/components/card';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@slyk/ui/components/table';
import { Badge } from '@slyk/ui/components/badge';
import { useApi, authedPost } from '@/lib/use-api';
import { useAuth } from '@/lib/auth-context';

interface Bet {
  id: number;
  event: string;
  stake: string;
  odds: string;
  status: string;
  payout: string;
  placed_at: string;
}

interface BetsResponse { results?: Bet[] }

const STATUS_VARIANT: Record<string, 'default' | 'secondary' | 'destructive'> = {
  open: 'default',
  won: 'default',
  lost: 'destructive',
  void: 'secondary',
  pending: 'secondary',
};

export default function BettingFeedsPage() {
  const { accessToken } = useAuth();
  const { data, loading, refetch } = useApi<BetsResponse>('/admin/bets/');
  const bets = data?.results ?? [];
  const [settling, setSettling] = useState<number | null>(null);

  async function settle(betId: number, outcome: 'won' | 'lost' | 'void') {
    if (!accessToken) return;
    setSettling(betId);
    await authedPost(`/bets/${betId}/settle/`, { outcome }, accessToken);
    setSettling(null);
    refetch();
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold">Live Betting Feeds</h1>
        <p className="text-muted-foreground">Monitor incoming bets and odds movements across markets.</p>
      </div>

      {/* Live WebSocket streams */}
      <div className="grid gap-5 lg:grid-cols-2">
        <RealtimeFeed channel="admin:bets" title="Bet Placements" />
        <RealtimeFeed channel="odds" title="Odds Movements" />
      </div>

      {/* Recent bets from API */}
      <div>
        <h2 className="mb-3 text-lg font-semibold">Recent bets (all players)</h2>
        <Card className="p-2">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>ID</TableHead>
                <TableHead>Event</TableHead>
                <TableHead>Stake</TableHead>
                <TableHead>Odds</TableHead>
                <TableHead>Payout</TableHead>
                <TableHead>Status</TableHead>
                <TableHead>Placed</TableHead>
                <TableHead>Settle</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {loading && (
                <TableRow><TableCell colSpan={8} className="text-muted-foreground">Loading…</TableCell></TableRow>
              )}
              {!loading && bets.length === 0 && (
                <TableRow><TableCell colSpan={8} className="text-muted-foreground">No bets placed yet.</TableCell></TableRow>
              )}
              {bets.map((b) => (
                <TableRow key={b.id}>
                  <TableCell className="text-xs text-muted-foreground">#{b.id}</TableCell>
                  <TableCell className="max-w-[140px] truncate">{b.event}</TableCell>
                  <TableCell>{b.stake}</TableCell>
                  <TableCell>{b.odds}</TableCell>
                  <TableCell>{b.payout || '—'}</TableCell>
                  <TableCell>
                    <Badge variant={STATUS_VARIANT[b.status] ?? 'secondary'}>{b.status}</Badge>
                  </TableCell>
                  <TableCell className="text-xs text-muted-foreground">
                    {new Date(b.placed_at).toLocaleString()}
                  </TableCell>
                  <TableCell>
                    {b.status === 'pending' ? (
                      <div className="flex gap-1">
                        {(['won', 'lost', 'void'] as const).map((outcome) => (
                          <button
                            key={outcome}
                            onClick={() => settle(b.id, outcome)}
                            disabled={settling === b.id}
                            className={`rounded px-2 py-1 text-xs font-medium disabled:opacity-50 ${
                              outcome === 'won'
                                ? 'bg-green-600 text-white hover:bg-green-700'
                                : outcome === 'lost'
                                ? 'bg-red-600 text-white hover:bg-red-700'
                                : 'bg-muted hover:bg-accent'
                            }`}
                          >
                            {settling === b.id ? '…' : outcome}
                          </button>
                        ))}
                      </div>
                    ) : (
                      <span className="text-xs text-muted-foreground">—</span>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Card>
      </div>
    </div>
  );
}
