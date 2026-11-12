'use client';

import { useEffect, useState } from 'react';
import { Badge, Btn, Field, Notice, TextInput, money } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';
import { LoadingState } from '@slyk/ui/components/spinner';

type Tone = { tone: 'green' | 'red'; text: string } | null;

interface Health {
  last_run: string | null; running: boolean;
  last_close: string | null; closing: boolean; days_behind: { agents: number; days: number }; net_loss_since: string | null;
  missing_tickets: number; missing_amount: string; agents_affected: number;
}

interface StatementDay {
  day: string; customers: number; stakes: string; wins: string; bonus_conversions: string; open_adjustment: string;
  hedge: string; net_loss: string; carried_in: string; carry_out: string; rate: string; commission: string; status: string;
  sports_commission: string; casino_net_loss: string; casino_carried_in: string; casino_rate: string; casino_commission: string;
}
interface Statements { today: { net_loss: string; commission: string; carried_in: string; customers: number }; carry: string; days: StatementDay[] }

type State = 'credited' | 'waiting' | 'missing' | 'not_counted';
interface AuditRow {
  ticket: string; customer: string; stake: string; settled_at: string;
  state: State; reason: string; amount: string;
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
  net_loss: 'Paid in the daily net-loss close instead',
};

function ago(iso: string | null) {
  if (!iso) return 'never';
  const mins = Math.round((Date.now() - new Date(iso).getTime()) / 60000);
  if (mins < 1) return 'just now';
  if (mins < 60) return `${mins} min ago`;
  const hours = Math.round(mins / 60);
  return hours < 48 ? `${hours} h ago` : `${Math.round(hours / 24)} days ago`;
}

/** Top of the Affiliates tab: is the nightly close paying agents, and is anyone owed? */
export function CreditingHealth({ version = 0 }: { version?: number }) {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<Health>('/admin/affiliates/crediting-health/');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Tone>(null);
  // eslint-disable-next-line react-hooks/exhaustive-deps
  useEffect(() => { if (version) refetch(); }, [version]);
  if (!data) return null;

  async function closeNow() {
    if (!accessToken) return;
    setBusy(true);
    const res = await authedPost<{ credited: number; days: number }>('/admin/affiliates/credit-missed/', {}, accessToken);
    setBusy(false);
    setNotice(res.error ? { tone: 'red', text: res.error }
      : { tone: 'green', text: `Closed ${res.data?.days ?? 0} agent-days${res.data?.credited ? ` and credited ${res.data.credited} older losing tickets` : ''}.` });
    refetch();
  }

  const behind = data.days_behind.days > 0;
  const healthy = data.closing && !behind && data.missing_tickets === 0;
  return (
    <div className="space-y-2">
      <div className={`flex flex-wrap items-center gap-x-4 gap-y-2 rounded-xl border px-4 py-3 text-sm ${healthy ? 'border-border bg-card' : 'border-live/40 bg-live/5'}`}>
        <Badge tone={data.closing ? 'green' : 'red'} dot>{data.closing ? 'Nightly close is running' : 'Nightly close is not running'}</Badge>
        <span className="text-muted-foreground">Last run: {ago(data.last_close)}</span>
        {behind ? (
          <span className="font-semibold text-live">{data.days_behind.days} day{data.days_behind.days === 1 ? '' : 's'} not closed for {data.days_behind.agents} agent{data.days_behind.agents === 1 ? '' : 's'}</span>
        ) : <span className="text-muted-foreground">Every agent is paid up to yesterday.</span>}
        {data.missing_tickets > 0 && (
          <span className="font-semibold text-live">{data.missing_tickets} older losing tickets unpaid · {money(data.missing_amount)}</span>
        )}
        {(behind || data.missing_tickets > 0) && <Btn size="sm" variant="danger" busy={busy} onClick={closeNow} className="ml-auto">Close & pay now</Btn>}
      </div>
      {!data.closing && (
        <p className="text-xs text-muted-foreground">
          Agents are paid by the Celery beat and worker services every hour (each day closes after midnight). If this stays red, check that <code>celery_beat</code> and <code>celery_worker</code> are up — missed days are closed in order once they are.
        </p>
      )}
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}
    </div>
  );
}

/** An agent's closed days: what their customers lost and the commission, step by step. */
function StatementsTable({ id }: { id: number }) {
  const { data } = useApi<Statements>(`/admin/affiliates/${id}/statements/`);
  if (!data) return <LoadingState className="py-4" label="Loading daily earnings…" />;
  const neg = (v: string) => (Number(v) < 0 ? 'text-live' : '');
  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-semibold">Customers’ net loss (what commission is paid on)</span>
        <Badge tone="indigo">Today so far {money(data.today.net_loss)} → {money(data.today.commission)}</Badge>
        {Number(data.carry) < 0 && <Badge tone="red">Carried forward {money(data.carry)}</Badge>}
      </div>
      {data.days.length === 0 ? (
        <p className="text-xs text-muted-foreground">No closed days yet — the first closes after midnight.</p>
      ) : (
        <div className="max-h-80 overflow-auto rounded-xl border border-border bg-card">
          <table className="w-full text-xs tabular-nums">
            <thead className="sticky top-0 bg-card">
              <tr className="text-left text-muted-foreground">
                <th className="px-3 py-2 font-medium">Day</th>
                <th className="px-3 py-2 text-right font-medium">Stakes</th>
                <th className="px-3 py-2 text-right font-medium">Winnings</th>
                <th className="px-3 py-2 text-right font-medium" title="Stakes on bets still open at midnight count the day they settle">Open bets</th>
                <th className="px-3 py-2 text-right font-medium" title="Bonus money turned into Winnings">Bonus cost</th>
                <th className="px-3 py-2 text-right font-medium" title="Winnings of the agent's own account and of accounts sharing a payment number">Hedge</th>
                <th className="px-3 py-2 text-right font-medium">Sports net loss</th>
                <th className="px-3 py-2 text-right font-medium">Carried in</th>
                <th className="px-3 py-2 text-right font-medium" title="Aviator and casino games, at the programme's Aviator rate, with their own carry-forward">Aviator net loss</th>
                <th className="px-3 py-2 text-right font-medium">Commission</th>
              </tr>
            </thead>
            <tbody>
              {data.days.map((d) => (
                <tr key={d.day} className="border-t border-border/60">
                  <td className="px-3 py-2">{d.day} <span className="text-muted-foreground">· {d.customers}</span></td>
                  <td className="px-3 py-2 text-right">{money(d.stakes)}</td>
                  <td className="px-3 py-2 text-right">{Number(d.wins) ? `−${money(d.wins)}` : '—'}</td>
                  <td className={`px-3 py-2 text-right ${neg(d.open_adjustment)}`}>{money(d.open_adjustment)}</td>
                  <td className="px-3 py-2 text-right">{Number(d.bonus_conversions) ? `−${money(d.bonus_conversions)}` : '—'}</td>
                  <td className={`px-3 py-2 text-right ${neg(d.hedge)}`}>{Number(d.hedge) ? money(d.hedge) : '—'}</td>
                  <td className={`px-3 py-2 text-right font-semibold ${neg(d.net_loss)}`}>{money(d.net_loss)}</td>
                  <td className={`px-3 py-2 text-right ${neg(d.carried_in)}`}>{Number(d.carried_in) ? money(d.carried_in) : '—'}</td>
                  <td className={`px-3 py-2 text-right ${neg(d.casino_net_loss)}`} title={Number(d.casino_carried_in) ? `Carried in ${money(d.casino_carried_in)}` : undefined}>
                    {Number(d.casino_net_loss) ? money(d.casino_net_loss) : '—'}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {Number(d.commission) > 0 ? (
                      <span className="inline-flex items-center gap-1.5" title={`Sports ${money(d.sports_commission)} + Aviator & casino ${money(d.casino_commission)} (${Number(d.casino_rate)}%)`}>
                        {money(d.commission)}{d.status === 'pending' && <Badge tone="gold">needs approval</Badge>}
                      </span>
                    ) : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
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
      <StatementsTable id={id} />
      {loading && !data && <LoadingState className="py-4" label="Checking losing tickets…" />}
      {data && data.customers === 0 && (
        <p className="text-xs text-muted-foreground">
          No customers are linked to this agent. Players are linked only when they sign up through the agent’s link or type the code — link them below if they didn’t.
        </p>
      )}
      {data && data.losing_tickets > 0 && (
        <>
          <p className="text-xs font-semibold text-muted-foreground">Losing tickets paid one by one (before the switch to net loss)</p>
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
