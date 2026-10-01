'use client';

import { use, useState } from 'react';
import Link from 'next/link';
import { FaArrowLeft, FaUser } from 'react-icons/fa';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { useApi, authedPost } from '@/lib/use-api';

type PageProps = { params: Promise<{ id: string }> };

interface Player {
  id: number;
  username: string;
  email: string;
  kyc_status: string;
  balance: string;
  currency: string;
  created_at: string;
  avatar_url: string;
  loyalty_tier: string;
  is_suspended: boolean;
  suspended_reason: string;
  suspended_at: string | null;
}

interface LedgerEntry {
  id: number;
  amount: string;
  kind: string;
  reference: string;
  idempotency_key: string;
  created_at: string;
}

interface KYCSubmission {
  id: number;
  document_type: string;
  status: 'pending' | 'approved' | 'rejected';
  rejection_reason: string;
  submitted_at: string;
  reviewed_at: string | null;
  reviewed_by_username: string;
}

interface ListResponse<T> { results?: T[] }

function statusBadge(status: KYCSubmission['status']) {
  if (status === 'approved') return <Badge variant="success">Approved</Badge>;
  if (status === 'rejected') return <Badge variant="destructive">Rejected</Badge>;
  return <Badge variant="secondary">Pending</Badge>;
}

export default function PlayerDetailPage({ params }: PageProps) {
  const { id } = use(params);
  const { accessToken } = useAuth();

  const { data: player, loading, refetch } = useApi<Player>(`/players/${id}/`);
  const { data: ledgerData } = useApi<ListResponse<LedgerEntry>>(`/admin/ledger/?player_id=${id}`);
  const { data: kycData } = useApi<ListResponse<KYCSubmission>>(`/admin/kyc/?player_id=${id}`);
  const ledger = ledgerData?.results ?? [];
  const kycSubmissions = kycData?.results ?? [];

  const [suspendReason, setSuspendReason] = useState('');
  const [showSuspendForm, setShowSuspendForm] = useState(false);
  const [adjustAmount, setAdjustAmount] = useState('');
  const [adjustReason, setAdjustReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [actionError, setActionError] = useState('');

  async function handleSuspend() {
    if (!accessToken) return;
    setBusy(true);
    setActionError('');
    const { error } = await authedPost(`/players/${id}/suspend/`, { reason: suspendReason }, accessToken);
    setBusy(false);
    if (error) { setActionError(error); return; }
    setShowSuspendForm(false);
    setSuspendReason('');
    refetch();
  }

  async function handleUnsuspend() {
    if (!accessToken) return;
    setBusy(true);
    setActionError('');
    const { error } = await authedPost(`/players/${id}/unsuspend/`, {}, accessToken);
    setBusy(false);
    if (error) { setActionError(error); return; }
    refetch();
  }

  async function handleAdjustBalance(e: React.FormEvent) {
    e.preventDefault();
    if (!accessToken || !adjustAmount || !adjustReason) return;
    setBusy(true);
    setActionError('');
    const { error } = await authedPost(
      `/players/${id}/adjust-balance/`,
      { amount: adjustAmount, reason: adjustReason },
      accessToken,
    );
    setBusy(false);
    if (error) { setActionError(error); return; }
    setAdjustAmount('');
    setAdjustReason('');
    refetch();
  }

  if (loading) return <p className="p-4 text-sm text-muted-foreground">Loading player…</p>;
  if (!player) return <p className="p-4 text-sm text-destructive">Player not found.</p>;

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2.5">
        <Link href="/users" className="flex h-8 w-8 items-center justify-center rounded-full border border-border hover:bg-accent">
          <FaArrowLeft size={12} />
        </Link>
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gold/15 text-gold">
          <FaUser size={13} />
        </span>
        <div>
          <h1 className="text-2xl font-bold">{player.username}</h1>
          <p className="text-sm text-muted-foreground">{player.email}</p>
        </div>
        {player.is_suspended ? <Badge variant="destructive">Suspended</Badge> : <Badge variant="success">Active</Badge>}
      </div>

      {actionError && <p className="text-sm text-destructive">{actionError}</p>}

      <div className="grid gap-4 sm:grid-cols-3">
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">Balance</p>
            <p className="text-xl font-bold">{player.balance} {player.currency}</p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">KYC status</p>
            <p className="text-xl font-bold"><Badge variant="outline">{player.kyc_status}</Badge></p>
          </CardContent>
        </Card>
        <Card>
          <CardContent className="p-4">
            <p className="text-xs text-muted-foreground">Joined</p>
            <p className="text-xl font-bold">{new Date(player.created_at).toLocaleDateString()}</p>
          </CardContent>
        </Card>
      </div>

      <Card>
        <CardHeader><CardTitle className="text-base">Suspension</CardTitle></CardHeader>
        <CardContent className="space-y-3">
          {player.is_suspended && (
            <p className="text-sm text-muted-foreground">
              Suspended{player.suspended_at && ` on ${new Date(player.suspended_at).toLocaleString()}`}
              {player.suspended_reason && ` — ${player.suspended_reason}`}
            </p>
          )}
          {player.is_suspended ? (
            <button
              onClick={handleUnsuspend}
              disabled={busy}
              className="rounded-md border border-emerald-600 text-emerald-600 px-4 py-2 text-sm font-medium hover:bg-emerald-600/10 disabled:opacity-50"
            >
              Unsuspend player
            </button>
          ) : showSuspendForm ? (
            <div className="flex flex-col gap-2 sm:max-w-md">
              <input
                type="text"
                autoFocus
                value={suspendReason}
                onChange={(e) => setSuspendReason(e.target.value)}
                placeholder="Reason (optional)"
                className="rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
              <div className="flex gap-2">
                <button
                  onClick={handleSuspend}
                  disabled={busy}
                  className="rounded-md border border-destructive text-destructive px-4 py-2 text-sm font-medium hover:bg-destructive/10 disabled:opacity-50"
                >
                  Confirm suspend
                </button>
                <button
                  onClick={() => setShowSuspendForm(false)}
                  className="rounded-md border border-border px-4 py-2 text-sm font-medium hover:bg-accent"
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              onClick={() => setShowSuspendForm(true)}
              className="rounded-md border border-destructive text-destructive px-4 py-2 text-sm font-medium hover:bg-destructive/10"
            >
              Suspend player
            </button>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Adjust balance</CardTitle></CardHeader>
        <CardContent>
          <form onSubmit={handleAdjustBalance} className="grid gap-3 sm:grid-cols-3">
            <div className="space-y-1">
              <label className="text-sm font-medium">Amount</label>
              <input
                type="number" step="0.01"
                value={adjustAmount}
                onChange={(e) => setAdjustAmount(e.target.value)}
                placeholder="10.00 or -10.00"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div className="space-y-1 sm:col-span-2">
              <label className="text-sm font-medium">Reason</label>
              <input
                type="text"
                value={adjustReason}
                onChange={(e) => setAdjustReason(e.target.value)}
                placeholder="Goodwill credit for chat support escalation"
                className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
              />
            </div>
            <div>
              <button
                type="submit"
                disabled={busy || !adjustAmount || !adjustReason}
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
              >
                Apply adjustment
              </button>
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">KYC submissions</CardTitle></CardHeader>
        <CardContent className="p-0">
          {kycSubmissions.length === 0 && (
            <p className="p-4 text-sm text-muted-foreground">No KYC submissions.</p>
          )}
          {kycSubmissions.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Document</th>
                  <th className="px-4 py-3 font-medium">Submitted</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {kycSubmissions.map((s) => (
                  <tr key={s.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-3">{s.document_type}</td>
                    <td className="px-4 py-3 text-muted-foreground">{new Date(s.submitted_at).toLocaleString()}</td>
                    <td className="px-4 py-3">
                      {statusBadge(s.status)}
                      {s.status === 'rejected' && s.rejection_reason && (
                        <p className="mt-1 text-xs text-muted-foreground">Reason: {s.rejection_reason}</p>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>

      <Card>
        <CardHeader><CardTitle className="text-base">Ledger history</CardTitle></CardHeader>
        <CardContent className="p-0">
          {ledger.length === 0 && (
            <p className="p-4 text-sm text-muted-foreground">No ledger entries.</p>
          )}
          {ledger.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Kind</th>
                  <th className="px-4 py-3 font-medium">Amount</th>
                  <th className="px-4 py-3 font-medium">Reference</th>
                  <th className="px-4 py-3 font-medium">Date</th>
                </tr>
              </thead>
              <tbody>
                {ledger.map((e) => (
                  <tr key={e.id} className="border-b border-border last:border-0">
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
    </div>
  );
}
