'use client';

import { useState } from 'react';
import { FaIdCard } from 'react-icons/fa';
import { Card, CardContent } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { useApi, authedPost } from '@/lib/use-api';
import { config } from '@/lib/config';

interface KYCSubmission {
  id: number;
  player: number;
  username: string;
  document_type: string;
  status: 'pending' | 'approved' | 'rejected';
  rejection_reason: string;
  submitted_at: string;
  reviewed_at: string | null;
  reviewed_by_username: string;
}

interface KYCResponse { results?: KYCSubmission[] }

const STATUS_FILTERS = [
  { id: 'pending', label: 'Pending' },
  { id: 'approved', label: 'Approved' },
  { id: 'rejected', label: 'Rejected' },
  { id: '', label: 'All' },
] as const;

const DOCUMENT_LABELS: Record<string, string> = {
  passport: 'Passport',
  national_id: 'National ID',
  driving_license: 'Driving license',
  proof_of_address: 'Proof of address',
};

function statusBadge(status: KYCSubmission['status']) {
  if (status === 'approved') return <Badge variant="success">Approved</Badge>;
  if (status === 'rejected') return <Badge variant="destructive">Rejected</Badge>;
  return <Badge variant="secondary">Pending</Badge>;
}

export default function KYCReviewPage() {
  const { accessToken } = useAuth();
  const [statusFilter, setStatusFilter] = useState<string>('pending');
  const { data, loading, refetch } = useApi<KYCResponse>(`/admin/kyc/?status=${statusFilter}`);
  const submissions = data?.results ?? [];

  const [busyId, setBusyId] = useState<number | null>(null);
  const [rejectingId, setRejectingId] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState('');
  const [actionError, setActionError] = useState('');

  async function viewDocument(id: number) {
    if (!accessToken) return;
    setActionError('');
    try {
      const res = await fetch(`${config.apiUrl}/admin/kyc/${id}/document/`, {
        headers: { Authorization: `Bearer ${accessToken}` },
      });
      if (!res.ok) throw new Error(`API ${res.status}`);
      const blob = await res.blob();
      const url = URL.createObjectURL(blob);
      window.open(url, '_blank');
    } catch (e) {
      setActionError(e instanceof Error ? e.message : 'Failed to load document');
    }
  }

  async function handleApprove(id: number) {
    if (!accessToken) return;
    setBusyId(id);
    setActionError('');
    const { error } = await authedPost(`/admin/kyc/${id}/approve/`, {}, accessToken);
    setBusyId(null);
    if (error) { setActionError(error); return; }
    refetch();
  }

  function startReject(id: number) {
    setRejectingId(id);
    setRejectReason('');
    setActionError('');
  }

  async function handleReject(id: number) {
    if (!accessToken || !rejectReason.trim()) return;
    setBusyId(id);
    setActionError('');
    const { error } = await authedPost(`/admin/kyc/${id}/reject/`, { reason: rejectReason }, accessToken);
    setBusyId(null);
    if (error) { setActionError(error); return; }
    setRejectingId(null);
    setRejectReason('');
    refetch();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2.5">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gold/15 text-gold">
          <FaIdCard size={13} />
        </span>
        <div>
          <h1 className="text-2xl font-bold">KYC Review</h1>
          <p className="text-muted-foreground text-sm">Manual document review — no external provider is used.</p>
        </div>
      </div>

      <div className="flex gap-1 rounded-md bg-muted p-1 w-fit">
        {STATUS_FILTERS.map((f) => (
          <button
            key={f.id}
            onClick={() => setStatusFilter(f.id)}
            className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
              statusFilter === f.id ? 'bg-primary text-primary-foreground' : 'text-muted-foreground hover:text-foreground'
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {actionError && <p className="text-sm text-red-500">{actionError}</p>}

      <Card>
        <CardContent className="p-0">
          {loading && <p className="p-4 text-sm text-muted-foreground">Loading submissions…</p>}
          {!loading && submissions.length === 0 && (
            <p className="p-4 text-sm text-muted-foreground">No submissions for this filter.</p>
          )}
          {submissions.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Player</th>
                  <th className="px-4 py-3 font-medium">Document</th>
                  <th className="px-4 py-3 font-medium">Submitted</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {submissions.map((s) => (
                  <tr key={s.id} className="border-b border-border last:border-0 align-top">
                    <td className="px-4 py-3 font-medium">{s.username}</td>
                    <td className="px-4 py-3">{DOCUMENT_LABELS[s.document_type] ?? s.document_type}</td>
                    <td className="px-4 py-3 text-muted-foreground">{new Date(s.submitted_at).toLocaleString()}</td>
                    <td className="px-4 py-3">
                      {statusBadge(s.status)}
                      {s.status === 'rejected' && s.rejection_reason && (
                        <p className="mt-1 text-xs text-muted-foreground">Reason: {s.rejection_reason}</p>
                      )}
                      {s.reviewed_by_username && (
                        <p className="mt-1 text-xs text-muted-foreground">By {s.reviewed_by_username}</p>
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex flex-col gap-2">
                        <button
                          onClick={() => viewDocument(s.id)}
                          className="w-fit rounded px-2 py-1 text-xs border border-border hover:bg-accent"
                        >
                          View document
                        </button>
                        {s.status === 'pending' && rejectingId !== s.id && (
                          <div className="flex gap-2">
                            <button
                              onClick={() => handleApprove(s.id)}
                              disabled={busyId === s.id}
                              className="rounded px-2 py-1 text-xs border border-emerald-600 text-emerald-600 hover:bg-emerald-600/10 disabled:opacity-50"
                            >
                              Approve
                            </button>
                            <button
                              onClick={() => startReject(s.id)}
                              disabled={busyId === s.id}
                              className="rounded px-2 py-1 text-xs border border-destructive text-destructive hover:bg-destructive/10 disabled:opacity-50"
                            >
                              Reject
                            </button>
                          </div>
                        )}
                        {rejectingId === s.id && (
                          <div className="flex flex-col gap-2 w-56">
                            <input
                              type="text"
                              autoFocus
                              value={rejectReason}
                              onChange={(e) => setRejectReason(e.target.value)}
                              placeholder="Rejection reason"
                              className="rounded-md border border-border bg-background px-2 py-1 text-xs focus:outline-none focus:ring-2 focus:ring-primary"
                            />
                            <div className="flex gap-2">
                              <button
                                onClick={() => handleReject(s.id)}
                                disabled={busyId === s.id || !rejectReason.trim()}
                                className="rounded px-2 py-1 text-xs border border-destructive text-destructive hover:bg-destructive/10 disabled:opacity-50"
                              >
                                Confirm reject
                              </button>
                              <button
                                onClick={() => setRejectingId(null)}
                                className="rounded px-2 py-1 text-xs border border-border hover:bg-accent"
                              >
                                Cancel
                              </button>
                            </div>
                          </div>
                        )}
                      </div>
                    </td>
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
