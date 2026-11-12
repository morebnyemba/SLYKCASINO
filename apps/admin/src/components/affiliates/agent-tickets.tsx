'use client';

import { useEffect, useState } from 'react';
import { Badge, Btn, Field, Notice, TextInput, money } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';
import { LoadingState } from '@slyk/ui/components/spinner';

type Tone = { tone: 'green' | 'red'; text: string } | null;

interface Health {
  last_run: string | null; running: boolean;
  missing_tickets: number; missing_amount: string; agents_affected: number;
}

type State = 'credited' | 'waiting' | 'missing' | 'not_counted';
interface AuditRow {
  ticket: string; customer: string; stake: string; settled_at: string;
  state: State; reason: '' | 'before_link' | 'agent_inactive' | 'zero_rate'; amount: string;
}
interface Audit {
  days: number; customers: number; losing_tickets: number;
  counts: Record<State, number>; missing_amount: string; tickets: AuditRow[];
}

const STATE: Record<State, { label: string; tone: 'green' | 'red' | 'gold' | 'slate' }> = {
  credited: { label: 'Credited', tone: 'green' },
  waiting: { label: 'Crediting in a few minutes', tone: 'gold' },
  missing: { label: 'Missed — not paid yet', tone: 'red' },
  not_counted: { label: 'Not counted', tone: 'slate' },
};
const REASON: Record<string, string> = {
  before_link: 'Lost before the customer was linked to this agent',
  agent_inactive: 'Lost while the agent was pending or suspended',
  zero_rate: 'Agent’s commission rate is 0%',
};

function ago(iso: string | null) {
  if (!iso) return 'never';
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  return hours < 48 ? `${hours} h ago` : `${Math.round(hours / 24)} days ago`;
}

/** Top of the Affiliates tab: is the job that pays agents for lost tickets running, and is anyone owed? */
export function CreditingHealth({ version = 0 }: { version?: number }) {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<Health>('/admin/affiliates/crediting-health/');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Tone>(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (version) refetch(); }, [version]);
  if (!data) return null;

  async function creditAll() {
    if (!accessToken) return;
    setBusy(true);
    const res = await authedPost<{ credited: number }>('/admin/affiliates/credit-missed/', {}, accessToken);
    setBusy(false);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: `Credited ${res.data?.credited ?? 0} missed losing tickets.` });
    refetch();
  }

  const healthy = data.running && data.missing_tickets === 0;
  return (
    <div className="space-y-2">
      <div className={`flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border px-4 py-3 text-sm ${healthy ? 'border-border bg-card' : 'border-live/40 bg-live/5'}`}>
        <Badge tone={data.running ? 'green' : 'red'} dot>{data.running ? 'Crediting is running' : 'Crediting job is not running'}</Badge>
        <span className="text-muted-foreground">Last run: {ago(data.last_run)}</span>
        {data.missing_tickets > 0 ? (
          <span className="font-semibold text-live">
            {data.missing_tickets} losing ticket{data.missing_tickets === 1 ? '' : 's'} not credited · {money(data.missing_amount)} owed to {data.agents_affected} agent{data.agents_affected === 1 ? '' : 's'}
          </span>
        ) : <span className="text-muted-foreground">Every losing ticket of the last 35 days is credited.</span>}
        {data.missing_tickets > 0 && <Btn size="sm" variant="danger" busy={busy} onClick={creditAll} className="ml-auto">Credit missed tickets</Btn>}
      </div>
      {!data.running && (
        <p className="text-xs text-muted-foreground">
          Agents are paid by the Celery beat and worker services every minute. If this stays red, check that <code>celery_beat</code> and <code>celery_worker</code> are up — an hourly catch-up pays anything missed once they are.
        </p>
      )}
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}
    </div>
  );
}

/** One agent: each losing ticket of their customers and whether it was paid, plus recovery tools. */
export function AgentTicketsPanel({ id, active, onChanged }: { id: number; active: boolean; onChanged?: () => void }) {
  const { accessToken } = useAuth();
  const { data, loading, refetch } = useApi<Audit>(`/admin/affiliates/${id}/tickets-audit/`);
  const [busy, setBusy] = useState<'credit' | 'link' | null>(null);
  const [notice, setNotice] = useState<Tone>(null);
  const [player, setPlayer] = useState('');
  const [from, setFrom] = useState('');

  async function creditMissed() {
    if (!accessToken) return;
    setBusy('credit');
    const res = await authedPost<{ credited: number }>(`/admin/affiliates/${id}/credit-missed/`, {}, accessToken);
    setBusy(null);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: `Credited ${res.data?.credited ?? 0} tickets.` });
    refetch(); onChanged?.();
  }

  async function link() {
    if (!accessToken || !player.trim()) return;
    const when = from ? `losing tickets from ${from} count` : 'only tickets lost from now on count';
    if (!window.confirm(`Link “${player.trim()}” to this agent? ${when}. A customer of another agent moves here; what that agent was already paid stays theirs.`)) return;
    setBusy('link');
    const res = await authedPost<{ player: string; previous_agent: string | null; credited: number }>(
      `/admin/affiliates/${id}/link-customer/`, { player: player.trim(), credit_from: from || null }, accessToken);
    setBusy(null);
    if (res.error) { setNotice({ tone: 'red', text: res.error }); return; }
    const d = res.data!;
    setNotice({ tone: 'green', text: `${d.player} linked${d.previous_agent ? ` (moved from ${d.previous_agent})` : ''}; ${d.credited} past ticket${d.credited === 1 ? '' : 's'} credited.` });
    setPlayer(''); setFrom('');
    refetch(); onChanged?.();
  }

  return (
    <div className="space-y-4 bg-muted/40 px-4 py-4">
      {loading && !data && <LoadingState className="py-4" label="Checking losing tickets…" />}
      {data && (
        <>
          <div className="flex flex-wrap items-center gap-2 text-xs">
            <span className="font-semibold">Last {data.days} days · {data.customers} customers · {data.losing_tickets} losing tickets:</span>
            <Badge tone="green">{data.counts.credited} credited</Badge>
            {data.counts.waiting > 0 && <Badge tone="gold">{data.counts.waiting} crediting</Badge>}
            <Badge tone={data.counts.missing ? 'red' : 'slate'}>{data.counts.missing} missed{data.counts.missing ? ` · ${money(data.missing_amount)}` : ''}</Badge>
            <Badge tone="slate">{data.counts.not_counted} not counted</Badge>
            {data.counts.missing > 0 && active && (
              <Btn size="sm" variant="danger" busy={busy === 'credit'} onClick={creditMissed} className="ml-auto">Credit missed tickets</Btn>
            )}
          </div>
          {data.customers === 0 && (
            <p className="text-xs text-muted-foreground">
              No customers are linked to this agent. Players are linked only when they sign up through the agent’s link or type the code — link them below if they didn’t.
            </p>
          )}
          {data.tickets.length > 0 && (
            <div className="max-h-80 overflow-auto rounded-xl border border-border bg-card">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-card">
                  <tr className="text-left text-muted-foreground">
                    <th className="px-3 py-2 font-medium">Ticket</th>
                    <th className="px-3 py-2 font-medium">Customer</th>
                    <th className="px-3 py-2 text-right font-medium">Stake</th>
                    <th className="px-3 py-2 font-medium">Lost</th>
                    <th className="px-3 py-2 font-medium">Agent share</th>
                  </tr>
                </thead>
                <tbody>
                  {data.tickets.map((t) => (
                    <tr key={t.ticket} className="border-t border-border/60">
                      <td className="px-3 py-2 font-mono">{t.ticket}</td>
                      <td className="px-3 py-2">{t.customer}</td>
                      <td className="px-3 py-2 text-right tabular-nums">{money(t.stake)}</td>
                      <td className="px-3 py-2 text-muted-foreground">{new Date(t.settled_at).toLocaleString()}</td>
                      <td className="px-3 py-2">
                        <span className="inline-flex flex-wrap items-center gap-2">
                          <Badge tone={STATE[t.state].tone}>{STATE[t.state].label}</Badge>
                          {t.state !== 'not_counted' && <span className="tabular-nums">{money(t.amount)}</span>}
                          {t.reason && <span className="text-muted-foreground">{REASON[t.reason] ?? t.reason}</span>}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
      {active && (
        <div className="rounded-xl border border-border bg-card p-3">
          <p className="mb-2 text-xs font-bold">Link a customer to this agent</p>
          <p className="mb-3 text-xs text-muted-foreground">
            For a player who came through this agent but signed up without the link (e.g. opened it in WhatsApp, registered later in another browser). Every link is recorded in the audit log.
          </p>
          <div className="flex flex-wrap items-end gap-3">
            <Field label="Username, email or player ID"><TextInput value={player} onChange={(e) => setPlayer(e.target.value)} placeholder="e.g. tinashe77" /></Field>
            <Field label="Count losing tickets from (optional)"><TextInput type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
            <Btn variant="primary" busy={busy === 'link'} disabled={!player.trim()} onClick={link}>Link customer</Btn>
          </div>
        </div>
      )}
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}
    </div>
  );
}
