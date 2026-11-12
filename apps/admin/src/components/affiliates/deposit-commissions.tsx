'use client';

import { useState } from 'react';
import { Badge, Btn, Notice, money } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';
import { LoadingState } from '@slyk/ui/components/spinner';

type State = 'paid' | 'pending' | 'due' | 'not_yet';
interface Row {
  player_id: number; customer: string; joined: string; first_deposit: string | null; deposits: string; turnover: string;
  state: State; amount: string; reason: string;
}
interface Audit {
  terms: { cpa_percent: string; cpa_cap: string; cpa_amount: string; cpa_min_deposit: string; turnover_multiple: string };
  counts: Record<State, number>; due_total: string; customers: Row[];
}
const STATE: Record<State, { label: string; tone: 'green' | 'gold' | 'red' | 'slate' }> = {
  paid: { label: 'Paid', tone: 'green' }, pending: { label: 'Waiting for approval', tone: 'gold' },
  due: { label: 'Due — not paid yet', tone: 'red' }, not_yet: { label: 'Not earned yet', tone: 'slate' },
};

/** One agent's deposit commission for every customer they ever referred, with tools to pay what was missed. */
export function DepositCommissionsPanel({ id, active, onChanged }: { id: number; active: boolean; onChanged?: () => void }) {
  const { accessToken } = useAuth();
  const { data, loading, refetch } = useApi<Audit>(`/admin/affiliates/${id}/deposit-commissions/`);
  const [picked, setPicked] = useState<number[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);

  async function pay(body: { player_ids?: number[]; override?: boolean }, confirmText: string) {
    if (!accessToken || !window.confirm(confirmText)) return;
    setBusy(true);
    const res = await authedPost<{ created: number; approved: number; amount: string }>(
      `/admin/affiliates/${id}/deposit-commissions/`, body, accessToken);
    setBusy(false);
    if (res.error) { setNotice({ tone: 'red', text: res.error }); return; }
    const d = res.data!;
    setNotice({ tone: 'green', text: `Paid ${money(d.amount)} — ${d.created} new${d.approved ? `, ${d.approved} approved` : ''}. It’s in the agent’s wallet.` });
    setPicked([]);
    refetch(); onChanged?.();
  }

  if (loading && !data) return <LoadingState className="py-4" label="Checking deposit commissions…" />;
  if (!data) return null;
  const t = data.terms;
  const due = data.counts.due + data.counts.pending;
  const toggle = (pid: number) => setPicked((p) => (p.includes(pid) ? p.filter((x) => x !== pid) : [...p, pid]));
  return (
    <div className="space-y-3 bg-muted/40 px-4 py-4">
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <span className="font-semibold">Deposit commission since the first referral · terms: {Number(t.cpa_percent)}% of first deposit{Number(t.cpa_cap) > 0 && ` (max ${money(t.cpa_cap)})`}{Number(t.cpa_amount) > 0 && ` + ${money(t.cpa_amount)}`}, once deposits reach {money(t.cpa_min_deposit)} and they’ve bet {Number(t.turnover_multiple)}× their first deposit</span>
        <Badge tone="green">{data.counts.paid} paid</Badge>
        {data.counts.pending > 0 && <Badge tone="gold">{data.counts.pending} waiting</Badge>}
        <Badge tone={data.counts.due ? 'red' : 'slate'}>{data.counts.due} due{data.counts.due ? ` · ${money(data.due_total)}` : ''}</Badge>
        <Badge tone="slate">{data.counts.not_yet} not earned yet</Badge>
      </div>
      {Number(t.cpa_percent) <= 0 && Number(t.cpa_amount) <= 0 && (
        <p className="text-xs text-live">This agent’s terms pay no deposit commission. Set a % under Terms first, then come back here.</p>
      )}
      {data.customers.length === 0 ? <p className="text-xs text-muted-foreground">No customers linked to this agent.</p> : (
        <div className="max-h-96 overflow-auto rounded-xl border border-border bg-card">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-card">
              <tr className="text-left text-muted-foreground">
                <th className="w-8 px-3 py-2" />
                <th className="px-3 py-2 font-medium">Customer</th>
                <th className="px-3 py-2 text-right font-medium">First deposit</th>
                <th className="px-3 py-2 text-right font-medium">All deposits</th>
                <th className="px-3 py-2 text-right font-medium">Bet</th>
                <th className="px-3 py-2 font-medium">Deposit commission</th>
              </tr>
            </thead>
            <tbody>
              {data.customers.map((r) => (
                <tr key={r.player_id} className="border-t border-border/60">
                  <td className="px-3 py-2">
                    {r.state === 'not_yet' && r.first_deposit && active && (
                      <input type="checkbox" checked={picked.includes(r.player_id)} onChange={() => toggle(r.player_id)} aria-label={`Pick ${r.customer}`} />
                    )}
                  </td>
                  <td className="px-3 py-2">{r.customer}<span className="block text-muted-foreground">joined {new Date(r.joined).toLocaleDateString()}</span></td>
                  <td className="px-3 py-2 text-right tabular-nums">{r.first_deposit ? money(r.first_deposit) : '—'}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{money(r.deposits)}</td>
                  <td className="px-3 py-2 text-right tabular-nums">{money(r.turnover)}</td>
                  <td className="px-3 py-2">
                    <span className="inline-flex flex-wrap items-center gap-2">
                      <Badge tone={STATE[r.state].tone}>{STATE[r.state].label}</Badge>
                      {Number(r.amount) > 0 && <span className="tabular-nums">{r.state === 'not_yet' ? `would be ${money(r.amount)}` : money(r.amount)}</span>}
                      {r.reason && <span className="text-muted-foreground">{r.reason}</span>}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {active && (
        <div className="flex flex-wrap items-center gap-2">
          <Btn size="sm" variant="primary" busy={busy} disabled={!due}
            onClick={() => pay({}, `Pay every deposit commission this agent has earned but not had (${money(data.due_total)} due${data.counts.pending ? ` + ${data.counts.pending} waiting for approval` : ''})?`)}>
            Pay all due{data.counts.due ? ` (${money(data.due_total)})` : ''}
          </Btn>
          <Btn size="sm" variant="danger" busy={busy} disabled={!picked.length}
            onClick={() => pay({ player_ids: picked, override: true }, `Pay ${picked.length} customer${picked.length === 1 ? '' : 's'} who haven’t met the deposit / play-through rules? This is recorded in the audit log.`)}>
            Pay {picked.length || ''} selected without the rules
          </Btn>
          <span className="text-xs text-muted-foreground">Tick customers marked “not earned yet” to pay them anyway.</span>
        </div>
      )}
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}
    </div>
  );
}
