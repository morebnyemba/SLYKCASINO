'use client';

import { useState } from 'react';
import Link from 'next/link';
import { FaHistory } from 'react-icons/fa';
import { Card, CardContent } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useApi } from '@/lib/use-api';

interface AuditLogEntry {
  id: number;
  player_id: number | null;
  event_type: string;
  ip_address: string | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

interface AuditLogResponse {
  count: number;
  results?: AuditLogEntry[];
}

const EVENT_TYPES = [
  '', 'login', 'logout', 'register', 'deposit', 'withdrawal', 'bet_placed', 'bet_settled',
  'casino_spin', 'promo_claim', 'self_exclude', 'limit_set', 'email_verified', 'password_reset',
  'data_export', 'account_deleted', 'kyc_submitted', 'kyc_approved', 'kyc_rejected',
  'player_suspended', 'player_unsuspended', 'balance_adjusted',
];

const PAGE_SIZE = 25;

export default function AuditLogPage() {
  const [eventType, setEventType] = useState('');
  const [playerId, setPlayerId] = useState('');
  const [page, setPage] = useState(1);

  const filters = `${eventType ? `&event_type=${eventType}` : ''}${playerId ? `&player_id=${playerId}` : ''}`;
  const { data, loading, error } = useApi<AuditLogResponse>(`/admin/audit-log/?page=${page}${filters}`);
  const entries = data?.results ?? [];
  const totalPages = data?.count ? Math.ceil(data.count / PAGE_SIZE) : 1;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2.5">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gold/15 text-gold">
          <FaHistory size={13} />
        </span>
        <h1 className="text-2xl font-bold">Audit Log</h1>
      </div>

      <div className="flex items-center gap-2">
        <select
          value={eventType}
          onChange={(e) => { setEventType(e.target.value); setPage(1); }}
          className="rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
        >
          {EVENT_TYPES.map((t) => <option key={t} value={t}>{t || 'All event types'}</option>)}
        </select>
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
          {loading && <p className="p-4 text-sm text-muted-foreground">Loading audit log…</p>}
          {!loading && entries.length === 0 && (
            <p className="p-4 text-sm text-muted-foreground">No audit entries.</p>
          )}
          {entries.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Event</th>
                  <th className="px-4 py-3 font-medium">Player</th>
                  <th className="px-4 py-3 font-medium">IP</th>
                  <th className="px-4 py-3 font-medium">Metadata</th>
                  <th className="px-4 py-3 font-medium">Date</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id} className="border-b border-border last:border-0 align-top">
                    <td className="px-4 py-3"><Badge variant="outline">{e.event_type}</Badge></td>
                    <td className="px-4 py-3">
                      {e.player_id ? (
                        <Link href={`/players/${e.player_id}`} className="text-gold hover:underline">#{e.player_id}</Link>
                      ) : '—'}
                    </td>
                    <td className="px-4 py-3 text-muted-foreground">{e.ip_address ?? '—'}</td>
                    <td className="px-4 py-3 text-xs text-muted-foreground font-mono">
                      {Object.keys(e.metadata ?? {}).length > 0 ? JSON.stringify(e.metadata) : '—'}
                    </td>
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
