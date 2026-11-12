'use client';

import Link from 'next/link';
import { useState } from 'react';
import { BsShieldCheck } from 'react-icons/bs';
import { usePolling } from '@slyk/ui/components/analytics';
import { Badge, Btn, EmptyState, Notice, Panel, TextInput, cx } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';

interface Change {
  id: number; label: string; requested_by: string; status: string; status_label: string; created_at: string;
  decided_at: string | null; expires_at: string; diff: { field: string; before: unknown; after: unknown }[];
  votes: { user: string; decision: 'approve' | 'reject'; note: string }[]; waiting_for: string[];
  result_detail: string; can_vote: boolean; can_cancel: boolean;
}
interface View { pending_for_me: number; changes: Change[] }

const TONE: Record<string, 'gold' | 'green' | 'red' | 'slate'> = {
  open: 'gold', applied: 'green', rejected: 'red', failed: 'red', cancelled: 'slate', superseded: 'slate', expired: 'slate',
};
const show = (v: unknown) => (v === null || v === undefined || v === '' ? '—' : typeof v === 'object' ? JSON.stringify(v) : String(v));

/** On every admin page: settings changes waiting for your co-signature. */
export function PendingChangesBar() {
  const { data, refetch } = useApi<View>('/admin/settings-changes/');
  usePolling(refetch, 60000, [refetch]);
  if (!data?.pending_for_me) return null;
  return (
    <div className="flex flex-wrap items-center gap-3 bg-gold/15 px-4 py-2 text-sm font-semibold">
      <BsShieldCheck className="text-gold" />
      <span className="flex-1">{data.pending_for_me} revenue-share settings change{data.pending_for_me === 1 ? '' : 's'} wait{data.pending_for_me === 1 ? 's' : ''} for your co-signature — nothing changes until every partner approves.</span>
      <Link href="/settings-changes" className="rounded-lg border border-border bg-card px-3 py-1 text-xs font-bold hover:bg-muted">Review</Link>
    </div>
  );
}

function Row({ c, onDone }: { c: Change; onDone: (t: { tone: 'green' | 'red'; text: string }) => void }) {
  const { accessToken } = useAuth();
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  async function act(body: Record<string, unknown>, ok: string) {
    if (!accessToken) return;
    setBusy(true);
    const res = await authedPost(`/admin/settings-changes/${c.id}/`, body, accessToken);
    setBusy(false);
    onDone(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: ok });
  }
  return (
    <div className={cx('space-y-3 rounded-xl border p-4', c.status === 'open' ? 'border-gold/40' : 'border-border/60')}>
      <div className="flex flex-wrap items-center gap-2">
        <p className="font-semibold">{c.label}</p>
        <Badge tone={TONE[c.status] ?? 'slate'} dot>{c.status_label}</Badge>
        <span className="ml-auto text-xs text-muted-foreground">
          Asked by <b className="text-foreground">{c.requested_by}</b>, {new Date(c.created_at).toLocaleString()}
          {c.status === 'open' && <> · expires {new Date(c.expires_at).toLocaleDateString()}</>}
        </span>
      </div>
      {c.diff.length > 0 ? (
        <div className="overflow-x-auto rounded-lg border border-border/60">
          <table className="w-full text-xs">
            <thead><tr className="text-left text-muted-foreground"><th className="px-3 py-1.5">Setting</th><th className="px-3 py-1.5">Now</th><th className="px-3 py-1.5">Would become</th></tr></thead>
            <tbody>
              {c.diff.map((d) => (
                <tr key={d.field} className="border-t border-border/40 align-top">
                  <td className="px-3 py-1.5 font-mono">{d.field}</td>
                  <td className="max-w-[320px] break-words px-3 py-1.5 text-muted-foreground">{show(d.before)}</td>
                  <td className="max-w-[320px] break-words px-3 py-1.5 font-semibold">{show(d.after)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="text-xs text-muted-foreground">No visible difference from the current values.</p>}
      <div className="flex flex-wrap gap-1.5 text-xs">
        {c.votes.map((v) => <Badge key={v.user} tone={v.decision === 'approve' ? 'green' : 'red'}>{v.user}: {v.decision === 'approve' ? 'approved' : `rejected — “${v.note}”`}</Badge>)}
        {c.waiting_for.map((u) => <Badge key={u} tone="slate">{u}: waiting</Badge>)}
      </div>
      {c.result_detail && <p className="text-xs text-live">{c.result_detail}</p>}
      {(c.can_vote || c.can_cancel) && (
        <div className="flex flex-wrap items-end gap-2 border-t border-border/50 pt-3">
          {c.can_vote && <>
            <TextInput value={note} onChange={(e) => setNote(e.target.value)} placeholder="Reason (required to reject)" className="h-8 min-w-[220px] flex-1 text-xs" />
            <Btn size="sm" variant="danger" busy={busy} onClick={() => act({ decision: 'reject', note }, 'Rejected — the change is dropped.')}>Reject</Btn>
            <Btn size="sm" variant="success" busy={busy} onClick={() => act({ decision: 'approve', note }, 'Co-signed.')}>Approve</Btn>
          </>}
          {c.can_cancel && <Btn size="sm" variant="ghost" busy={busy} onClick={() => act({ cancel: true }, 'Withdrawn.')}>Withdraw my change</Btn>}
        </div>
      )}
    </div>
  );
}

/** Every held settings change: what it would change, who asked, who has co-signed. */
export function SettingsChangesPanel() {
  const { data, refetch } = useApi<View>('/admin/settings-changes/');
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  const open = data?.changes.filter((c) => c.status === 'open') ?? [];
  const done = data?.changes.filter((c) => c.status !== 'open') ?? [];
  return (
    <div className="space-y-6">
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}
      <Panel title="Waiting for co-signatures" description="Revenue-share settings — each wallet’s share, who holds each wallet, the founder and the start date — change only when every partner approves. One rejection drops a change; unsigned changes expire after 7 days.">
        {!data ? <div className="h-24 animate-pulse rounded-xl bg-muted/30" /> : open.length === 0
          ? <EmptyState icon={BsShieldCheck} title="Nothing waiting">Saving the revenue-share settings sends the change here for the partners to approve.</EmptyState>
          : <div className="space-y-3">{open.map((c) => <Row key={c.id} c={c} onDone={(t) => { setNotice(t); refetch(); }} />)}</div>}
      </Panel>
      {done.length > 0 && (
        <Panel title="Decided" description="Applied, rejected, withdrawn, superseded or expired.">
          <div className="space-y-3">{done.map((c) => <Row key={c.id} c={c} onDone={(t) => { setNotice(t); refetch(); }} />)}</div>
        </Panel>
      )}
    </div>
  );
}
