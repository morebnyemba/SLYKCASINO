'use client';

import { useState } from 'react';
import { FaShieldAlt, FaUpload } from 'react-icons/fa';
import { Card, CardContent } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { useApi } from '@/lib/use-api';
import { config } from '@/lib/config';
import { apiRefresh, getStoredTokens, storeTokens } from '@/lib/auth';

interface KYCSubmission {
  id: number;
  document_type: string;
  status: 'pending' | 'approved' | 'rejected';
  rejection_reason: string;
  submitted_at: string;
  reviewed_at: string | null;
}

const DOCUMENT_TYPES = [
  { id: 'passport', label: 'Passport' },
  { id: 'national_id', label: 'National ID' },
  { id: 'driving_license', label: 'Driving license' },
  { id: 'proof_of_address', label: 'Proof of address' },
];

function statusBadge(status: KYCSubmission['status']) {
  if (status === 'approved') return <Badge variant="success">Approved</Badge>;
  if (status === 'rejected') return <Badge variant="destructive">Rejected</Badge>;
  return <Badge variant="secondary">Pending review</Badge>;
}

async function uploadKycDocument(documentType: string, file: File, token: string) {
  const form = new FormData();
  form.append('document_type', documentType);
  form.append('file', file);

  let res = await fetch(`${config.apiUrl}/players/me/kyc/`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${token}` },
    body: form,
  });

  if (res.status === 401) {
    const stored = getStoredTokens();
    if (stored?.refresh) {
      const refreshed = await apiRefresh(stored.refresh);
      storeTokens(refreshed);
      res = await fetch(`${config.apiUrl}/players/me/kyc/`, {
        method: 'POST',
        headers: { Authorization: `Bearer ${refreshed.access}` },
        body: form,
      });
    }
  }

  const json = await res.json().catch(() => ({}));
  if (!res.ok) {
    const msg = (json as { detail?: string }).detail
      ?? Object.values(json as Record<string, string[]>).flat().join(' ')
      ?? `API ${res.status}`;
    throw new Error(msg || `API ${res.status}`);
  }
}

export default function VerificationPage() {
  const { accessToken } = useAuth();
  const { data, loading, error, refetch } = useApi<KYCSubmission[]>('/players/me/kyc/');
  const submissions = data ?? [];

  const [documentType, setDocumentType] = useState('passport');
  const [file, setFile] = useState<File | null>(null);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState('');

  const hasPending = submissions.some((s) => s.status === 'pending');

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!accessToken || !file) return;
    setSubmitting(true);
    setSubmitError('');
    try {
      await uploadKycDocument(documentType, file, accessToken);
      setFile(null);
      refetch();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'Upload failed');
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div>
      <div className="mb-4 flex items-center gap-2.5">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gold/15 text-gold">
          <FaShieldAlt size={13} />
        </span>
        <h1 className="text-2xl font-bold">Identity verification</h1>
      </div>
      <p className="mb-6 text-sm text-muted-foreground">
        Verification is reviewed manually by our team — no external provider is used. Submit a clear photo
        or scan of a supported document and we&apos;ll review it shortly.
      </p>

      {!hasPending && (
        <Card className="rounded-2xl border-gold/20">
          <CardContent className="pt-6">
            <form onSubmit={handleSubmit} className="grid gap-3 sm:grid-cols-2">
              <div className="space-y-1">
                <label className="text-sm font-medium">Document type</label>
                <select
                  value={documentType}
                  onChange={(e) => setDocumentType(e.target.value)}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                >
                  {DOCUMENT_TYPES.map((d) => <option key={d.id} value={d.id}>{d.label}</option>)}
                </select>
              </div>
              <div className="space-y-1">
                <label className="text-sm font-medium">File</label>
                <input
                  type="file"
                  accept="image/*,.pdf"
                  required
                  onChange={(e) => setFile(e.target.files?.[0] ?? null)}
                  className="w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary"
                />
              </div>
              {submitError && <p className="col-span-2 text-sm text-destructive">{submitError}</p>}
              <div className="col-span-2">
                <button
                  type="submit"
                  disabled={submitting || !file}
                  className="flex items-center gap-2 rounded-md bg-gradient-to-br from-gold to-gold/70 px-4 py-2 text-sm font-bold text-gold-foreground shadow transition-transform hover:scale-[1.02] disabled:opacity-50 disabled:hover:scale-100"
                >
                  <FaUpload size={12} />
                  {submitting ? 'Uploading…' : 'Submit document'}
                </button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      {hasPending && (
        <Card className="rounded-2xl border-gold/20">
          <CardContent className="pt-6">
            <p className="text-sm text-muted-foreground">
              Your document is pending review. We&apos;ll update the status below once it&apos;s been checked.
            </p>
          </CardContent>
        </Card>
      )}

      <h2 className="mb-3 mt-6 text-lg font-semibold">Submission history</h2>
      {error && <p className="text-sm text-destructive">{error}</p>}
      <Card className="rounded-2xl border-gold/10">
        <CardContent className="p-0">
          {loading && <p className="p-4 text-sm text-muted-foreground">Loading…</p>}
          {!loading && submissions.length === 0 && (
            <p className="p-4 text-sm text-muted-foreground">No submissions yet.</p>
          )}
          {submissions.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Document</th>
                  <th className="px-4 py-3 font-medium">Submitted</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                </tr>
              </thead>
              <tbody>
                {submissions.map((s) => (
                  <tr key={s.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-3">{DOCUMENT_TYPES.find((d) => d.id === s.document_type)?.label ?? s.document_type}</td>
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
    </div>
  );
}
