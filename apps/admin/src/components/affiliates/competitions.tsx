'use client';

import { Fragment, useState } from 'react';
import { BsAward, BsPlusLg, BsTrash3 } from 'react-icons/bs';
import { Badge, Btn, EmptyState, Field, Notice, Panel, Switch, TextInput, cx, money, tableClass, tdClass, thClass, trClass } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost, authedRequest, useApi } from '@/lib/use-api';

interface Standing { affiliate_id: number; code: string; customers: number; deposits: string; percent: number; reached: boolean; won: boolean }
interface Competition {
  id: number; name: string; description: string; starts_on: string; ends_on: string; target_customers: number;
  target_deposits: string; min_customer_deposit: string; prize: string; active: boolean;
  status: 'upcoming' | 'running' | 'ended' | 'off'; winners: number; paid_total: string; standings?: Standing[];
}
const URL = '/admin/affiliate-competitions/';
const STATUS: Record<Competition['status'], { label: string; tone: 'green' | 'gold' | 'slate' }> = {
  running: { label: 'Running', tone: 'green' }, upcoming: { label: 'Upcoming', tone: 'gold' },
  ended: { label: 'Ended', tone: 'slate' }, off: { label: 'Off', tone: 'slate' },
};
const iso = (d: Date) => `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
const blank = () => {
  const now = new Date(); const end = new Date(); end.setDate(end.getDate() + 30);
  return { name: '', description: '', starts_on: iso(now), ends_on: iso(end), target_customers: '', target_deposits: '', min_customer_deposit: '', prize: '' };
};

/** Agent competitions: targets for new customers and/or their deposits in a date window, with a prize paid
 *  automatically to the agent's locked balance. Agents see them (with their progress) on their dashboard. */
export function CompetitionsTab() {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<{ competitions: Competition[] }>(URL);
  const [form, setForm] = useState(blank());
  const [open, setOpen] = useState<number | null>(null);
  const [detail, setDetail] = useState<Competition | null>(null);
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  const set = (k: keyof ReturnType<typeof blank>) => (e: React.ChangeEvent<HTMLInputElement>) => setForm((f) => ({ ...f, [k]: e.target.value }));
  const num = (k: keyof ReturnType<typeof blank>) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value.replace(/[^0-9.]/g, '') }));

  async function create() {
    if (!accessToken) return;
    setBusy('add'); setNotice(null);
    const res = await authedPost<Competition>(URL, {
      ...form, target_customers: Number(form.target_customers) || 0, target_deposits: form.target_deposits || '0',
      min_customer_deposit: form.min_customer_deposit || '0',
    }, accessToken);
    setBusy('');
    if (res.error) { setNotice({ tone: 'red', text: res.error }); return; }
    setNotice({ tone: 'green', text: `“${res.data?.name}” created. Agents see it now.` });
    setForm(blank());
    refetch();
  }
  async function patch(c: Competition, body: Record<string, unknown>, ok: string) {
    if (!accessToken) return;
    const res = await authedRequest<Competition>('PATCH', `${URL}${c.id}/`, accessToken, body);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: ok });
    refetch();
  }
  async function remove(c: Competition) {
    if (!accessToken || !confirm(`Delete “${c.name}”?`)) return;
    const res = await authedRequest('DELETE', `${URL}${c.id}/`, accessToken);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: 'Deleted.' });
    refetch();
  }
  async function show(c: Competition) {
    if (open === c.id) { setOpen(null); return; }
    setOpen(c.id); setDetail(null);
    if (!accessToken) return;
    const res = await authedRequest<Competition>('GET', `${URL}${c.id}/`, accessToken);
    if (res.data) setDetail(res.data);
  }

  const targets = (c: Competition) => [
    c.target_customers ? `${c.target_customers} new customers${Number(c.min_customer_deposit) > 0 ? ` (each deposits ${money(c.min_customer_deposit)}+)` : ''}` : '',
    Number(c.target_deposits) > 0 ? `${money(c.target_deposits)} customer deposits` : '',
  ].filter(Boolean).join(' and ');

  return (
    <div className="space-y-5">
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}
      <Panel title="New competition"
        description="Set a target for a date window: a number of new customers, an amount their customers deposit, or both (both must be reached). Every agent who reaches it gets the prize once, added automatically to their locked balance. Agents see it on their dashboard.">
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          <Field label="Name" className="lg:col-span-2"><TextInput value={form.name} maxLength={80} placeholder="e.g. December sprint" onChange={set('name')} /></Field>
          <Field label="From"><TextInput type="date" value={form.starts_on} onChange={set('starts_on')} /></Field>
          <Field label="Until (inclusive)"><TextInput type="date" value={form.ends_on} onChange={set('ends_on')} /></Field>
          <Field label="Target: new customers" hint="Leave empty if not used."><TextInput inputMode="numeric" value={form.target_customers} onChange={num('target_customers')} /></Field>
          <Field label="Target: customer deposits ($)" hint="Everything their customers deposit in the window."><TextInput inputMode="decimal" value={form.target_deposits} onChange={num('target_deposits')} /></Field>
          <Field label="Each new customer must deposit ($)" hint="Stops fake sign-ups winning. 0 = every sign-up counts."><TextInput inputMode="decimal" value={form.min_customer_deposit} onChange={num('min_customer_deposit')} /></Field>
          <Field label="Prize ($)" hint="Paid once per agent who reaches the target."><TextInput inputMode="decimal" value={form.prize} onChange={num('prize')} /></Field>
          <Field label="Short description (agents see it)" className="sm:col-span-2 lg:col-span-4">
            <TextInput value={form.description} maxLength={300} placeholder="e.g. Bring 10 customers who deposit $5 or more and win $50" onChange={set('description')} />
          </Field>
        </div>
        <div className="mt-4 flex justify-end">
          <Btn variant="primary" icon={BsPlusLg} busy={busy === 'add'} disabled={!form.name.trim() || !(Number(form.prize) > 0) || !(Number(form.target_customers) > 0 || Number(form.target_deposits) > 0)} onClick={create}>
            Create competition
          </Btn>
        </div>
      </Panel>

      <Panel title="Competitions" padded={false}>
        {!data ? <div className="h-24 animate-pulse bg-muted/30" /> : data.competitions.length === 0 ? (
          <EmptyState icon={BsAward} title="No competitions yet">Create one above and agents will see it on their dashboard.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className={tableClass}>
              <thead><tr>
                <th className={thClass}>Competition</th><th className={thClass}>Target</th><th className={thClass}>Prize</th>
                <th className={thClass}>Winners</th><th className={thClass}>Status</th><th className={cx(thClass, 'text-center')}>On</th><th className={thClass} />
              </tr></thead>
              <tbody>
                {data.competitions.map((c) => (
                  <Fragment key={c.id}>
                    <tr className={cx(trClass, !c.active && 'opacity-60')}>
                      <td className={tdClass}>
                        <p className="font-semibold">{c.name}</p>
                        <p className="text-xs text-muted-foreground">{c.starts_on} → {c.ends_on}</p>
                      </td>
                      <td className={cx(tdClass, 'text-xs')}>{targets(c)}</td>
                      <td className={cx(tdClass, 'font-semibold tabular-nums')}>{money(c.prize)}</td>
                      <td className={cx(tdClass, 'tabular-nums')}>{c.winners}{c.winners > 0 && <span className="text-xs text-muted-foreground"> · paid {money(c.paid_total)}</span>}</td>
                      <td className={tdClass}><Badge tone={STATUS[c.status].tone}>{STATUS[c.status].label}</Badge></td>
                      <td className={cx(tdClass, 'text-center')}>
                        <Switch checked={c.active} label={`${c.name} on`} onChange={(v) => patch(c, { active: v }, v ? 'Competition on.' : 'Competition off: agents no longer see it.')} />
                      </td>
                      <td className={cx(tdClass, 'whitespace-nowrap text-right')}>
                        <Btn size="sm" onClick={() => show(c)}>{open === c.id ? 'Hide standings' : 'Standings'}</Btn>
                        {c.winners === 0 && (
                          <button onClick={() => remove(c)} aria-label={`Delete ${c.name}`} className="ml-1 rounded-lg p-2 text-muted-foreground hover:bg-live/10 hover:text-live"><BsTrash3 size={13} /></button>
                        )}
                      </td>
                    </tr>
                    {open === c.id && (
                      <tr className="border-b border-border/60">
                        <td colSpan={7} className="bg-muted/20 px-4 py-3">
                          {!detail ? <p className="text-xs text-muted-foreground">Loading…</p> : (detail.standings ?? []).length === 0 ? (
                            <p className="text-xs text-muted-foreground">No agent has any progress yet.</p>
                          ) : (
                            <table className="w-full text-sm">
                              <thead><tr className="text-left text-xs text-muted-foreground"><th className="py-1">Agent</th><th>New customers</th><th>Customer deposits</th><th>Progress</th><th /></tr></thead>
                              <tbody>
                                {detail.standings!.map((s) => (
                                  <tr key={s.affiliate_id} className="border-t border-border/40">
                                    <td className="py-1.5 font-mono text-xs">{s.code}</td>
                                    <td className="tabular-nums">{s.customers}{c.target_customers ? ` / ${c.target_customers}` : ''}</td>
                                    <td className="tabular-nums">{money(s.deposits)}{Number(c.target_deposits) > 0 ? ` / ${money(c.target_deposits)}` : ''}</td>
                                    <td className="tabular-nums">{s.percent}%</td>
                                    <td>{s.won && <Badge tone="green">Won {money(c.prize)}</Badge>}</td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          )}
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </div>
  );
}

interface Balance { available: string; locked: string; unlocks_on: string | null; pending: string; in_payout: string; paid_out: string }

/** Add to or take from an agent's locked balance, with a reason the agent sees. */
export function AdjustBalancePanel({ id, onChanged }: { id: number; onChanged: () => void }) {
  const { accessToken } = useAuth();
  const [mode, setMode] = useState<'add' | 'take'>('add');
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('');
  const [balance, setBalance] = useState<Balance | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);

  async function apply() {
    if (!accessToken) return;
    setBusy(true); setNotice(null);
    const signed = (mode === 'take' ? '-' : '') + amount;
    const res = await authedPost<Balance>(`/admin/affiliates/${id}/adjust-locked/`, { amount: signed, reason }, accessToken);
    setBusy(false);
    if (res.error) { setNotice({ tone: 'red', text: res.error }); return; }
    setBalance(res.data ?? null);
    setNotice({ tone: 'green', text: `${mode === 'add' ? 'Added' : 'Took'} ${money(amount)}. Locked balance is now ${money(res.data?.locked ?? 0)}.` });
    setAmount(''); setReason('');
    onChanged();
  }

  return (
    <div className="space-y-3 bg-muted/20 p-4">
      <p className="text-sm font-bold">Adjust locked balance</p>
      <p className="text-xs text-muted-foreground">
        Adds to or takes from what this agent has locked (earned this month and not yet unlocked). It shows in their earnings with your reason.
        You can take at most what is locked now. Every adjustment is logged.
      </p>
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}
      {balance && (
        <p className="text-xs text-muted-foreground">
          Now: <b className="text-foreground">{money(balance.locked)}</b> locked · <b className="text-foreground">{money(balance.available)}</b> available
        </p>
      )}
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex overflow-hidden rounded-lg border border-border text-sm font-bold">
          {(['add', 'take'] as const).map((m) => (
            <button key={m} type="button" onClick={() => setMode(m)} aria-pressed={mode === m}
              className={cx('px-4 py-2', mode === m ? (m === 'add' ? 'bg-win text-win-foreground' : 'bg-live text-white') : 'text-muted-foreground')}>
              {m === 'add' ? '+ Add' : '− Take away'}
            </button>
          ))}
        </div>
        <Field label="Amount ($)" className="w-32"><TextInput inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ''))} /></Field>
        <Field label="Reason (the agent sees it)" className="min-w-[260px] flex-1"><TextInput value={reason} maxLength={255} placeholder="e.g. Top agent bonus · Correction for duplicate payment" onChange={(e) => setReason(e.target.value)} /></Field>
        <Btn variant={mode === 'add' ? 'primary' : 'danger'} busy={busy} disabled={!(Number(amount) > 0) || !reason.trim()} onClick={apply}>
          {mode === 'add' ? 'Add to locked balance' : 'Take from locked balance'}
        </Btn>
      </div>
    </div>
  );
}
