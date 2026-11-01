'use client';

import Link from 'next/link';
import { use, useState } from 'react';
import { BsDownload, BsPrinter, BsShieldExclamation } from 'react-icons/bs';
import { Badge, Btn, Field, Notice, PageHeader, Panel, TextInput } from '@/components/console/ui';
import { RiskReportView } from '@/components/risk/risk-report';
import { useAuth } from '@/lib/auth-context';
import { downloadReport, type RiskCase, type RiskReport } from '@/lib/risk';
import { authedPost, useApi } from '@/lib/use-api';

/** One fraud case: the full report, and the superuser's decision. */
export default function RiskCasePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = use(params);
  const { accessToken, user } = useAuth();
  const { data, loading, refetch } = useApi<{ case: RiskCase; report: RiskReport }>(`/admin/risk/cases/${id}/`);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);

  if (loading && !data) return <div className="h-60 animate-pulse rounded-2xl bg-muted/40" />;
  if (!data) return <p className="text-sm text-destructive">Case not found.</p>;
  const c = data.case;

  async function decide(decision: 'dismiss' | 'confirm') {
    if (!accessToken) return;
    const what = decision === 'dismiss'
      ? 'Dismiss this case? The player is reinstated, restrictions are lifted and held withdrawals released.'
      : 'Confirm fraud? The account stays suspended/restricted.';
    if (!window.confirm(what)) return;
    setBusy(true);
    const res = await authedPost(`/admin/risk/cases/${id}/decide/`, { decision, note }, accessToken);
    setBusy(false);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: decision === 'dismiss' ? 'Dismissed — player reinstated.' : 'Confirmed as fraud.' });
    refetch();
  }

  return (
    <div className="space-y-5">
      <PageHeader icon={BsShieldExclamation} eyebrow="Fraud & risk"
        title={`Case #${c.id} — ${c.username ?? `#${c.player_id}`}`}
        description={c.reason}
        actions={<>
          <Btn icon={BsPrinter} onClick={() => window.print()}>Print</Btn>
          <Btn icon={BsDownload} onClick={() => downloadReport(data.report, `fraud-case-${c.id}`)}>Download report</Btn>
        </>} />
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}
      <Panel title="Decision" description={`Opened ${new Date(c.created_at).toLocaleString()} · score ${c.score}`}>
        <div className="flex flex-wrap items-center gap-2">
          <Badge tone={c.action === 'suspended' ? 'red' : 'gold'} dot>{c.action_label}</Badge>
          <Badge tone={c.status === 'open' ? 'gold' : c.status === 'confirmed' ? 'red' : 'green'}>{c.status_label}</Badge>
          <Link href={`/players/${c.player_id}`} className="text-sm text-secondary hover:underline">Open player page</Link>
          <Link href="/risk" className="text-sm text-muted-foreground hover:underline">All cases</Link>
        </div>
        {c.status === 'open' ? (
          user?.isSuperuser ? (
            <div className="mt-4 space-y-3">
              <Field label="Note for the record" hint="Why you decided this — kept with the case.">
                <TextInput value={note} onChange={(e) => setNote(e.target.value)} placeholder="Checked deposits with EcoCash; same household, not fraud" />
              </Field>
              <div className="flex flex-wrap gap-2">
                <Btn variant="success" busy={busy} disabled={note.trim().length < 3} onClick={() => decide('dismiss')}>Dismiss &amp; reinstate</Btn>
                <Btn variant="danger" busy={busy} disabled={note.trim().length < 3} onClick={() => decide('confirm')}>Confirm fraud</Btn>
              </div>
            </div>
          ) : <p className="mt-3 text-sm text-muted-foreground">Only a superuser can close a case.</p>
        ) : (
          <p className="mt-3 text-sm">{c.status_label} by <b>{c.decided_by}</b> on {new Date(c.decided_at!).toLocaleString()}: {c.decision_note}</p>
        )}
      </Panel>
      <RiskReportView report={data.report} />
    </div>
  );
}
