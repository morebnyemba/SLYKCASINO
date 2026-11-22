'use client';

import { useState } from 'react';
import { BsPiggyBank } from 'react-icons/bs';
import { Btn, Field, Notice, Panel, StatTile, TextInput, money, tableClass, tdClass, thClass, trClass } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';

interface Savings {
  balance: string; saved_total: string; used_total: string; partner_pool_percent: string; held_percent: string;
  unheld_percent: string; today_estimate: string;
  days: { day: string; base: string; savings: string; unheld_percent: string }[];
  uses: { id: number; day: string; amount: string; note: string; recorded_by: string }[];
}
const URL = '/admin/revenue-share/savings/';
const pct = (v: string | number) => `${Number(v).toFixed(2).replace(/\.?0+$/, '')}%`;

/** Dashboard card: the Savings account balance. Hidden from anyone who can't see the revenue share (or while it's locked for them). */
export function SavingsCard() {
  const { data, error } = useApi<Savings>(URL);
  if (error || !data) return null;
  return (
    <StatTile icon={BsPiggyBank} tone="green" label="Savings account" value={money(data.balance)} href="/revenue-share"
      hint={`${pct(data.unheld_percent)} of GGR saved daily · +${money(data.today_estimate)} today so far`} />
  );
}

/** The Savings account: the part of the partner pool no shareholder holds, saved every day for future use. */
export function SavingsPanel({ canUse }: { canUse: boolean }) {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<Savings>(URL);
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  if (!data) return null;

  async function use() {
    if (!accessToken) return;
    setBusy(true); setNotice(null);
    const res = await authedPost<Savings>(URL, { amount, note }, accessToken);
    setBusy(false);
    if (res.error) { setNotice({ tone: 'red', text: res.error }); return; }
    setNotice({ tone: 'green', text: `${money(amount)} taken from the savings.` });
    setAmount(''); setNote('');
    refetch();
  }

  return (
    <Panel title="Savings account"
      description={`Shareholders get ${pct(data.partner_pool_percent)} of each day’s GGR between them, by their own shares. What no one holds — ${pct(data.unheld_percent)} now (${pct(data.held_percent)} held) — is saved here every day for future use instead of going to the operating pool.`}>
      {notice && <div className="mb-4"><Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice></div>}
      <div className="grid gap-3 sm:grid-cols-4">
        <StatTile icon={BsPiggyBank} tone="green" label="Balance" value={money(data.balance)} />
        <StatTile tone="indigo" label="Saved so far" value={money(data.saved_total)} />
        <StatTile tone="slate" label="Used" value={money(data.used_total)} />
        <StatTile tone="gold" label="Today so far" value={money(data.today_estimate)} hint="added when the day closes" />
      </div>

      {canUse && (
        <div className="mt-4 flex flex-wrap items-end gap-3 rounded-xl border border-dashed border-border p-4">
          <Field label="Use savings ($)" className="w-36">
            <TextInput inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ''))} />
          </Field>
          <Field label="What for" className="min-w-[240px] flex-1">
            <TextInput value={note} maxLength={300} placeholder="e.g. New server, marketing campaign" onChange={(e) => setNote(e.target.value)} />
          </Field>
          <Btn variant="primary" busy={busy} disabled={!(Number(amount) > 0) || !note.trim()} onClick={use}>Record use</Btn>
        </div>
      )}

      {(data.days.length > 0 || data.uses.length > 0) && (
        <div className="mt-4 grid gap-4 lg:grid-cols-2">
          <div className="overflow-x-auto rounded-xl border border-border/70">
            <table className={tableClass}>
              <thead><tr><th className={thClass}>Day</th><th className={thClass}>Unheld</th><th className={thClass}>Saved</th></tr></thead>
              <tbody>
                {data.days.map((d) => (
                  <tr key={d.day} className={trClass}>
                    <td className={tdClass}>{d.day}</td>
                    <td className={tdClass}>{pct(d.unheld_percent)}</td>
                    <td className={`${tdClass} font-semibold tabular-nums text-win`}>+{money(d.savings)}</td>
                  </tr>
                ))}
                {data.days.length === 0 && <tr><td colSpan={3} className="px-4 py-6 text-center text-sm text-muted-foreground">Nothing saved yet.</td></tr>}
              </tbody>
            </table>
          </div>
          <div className="overflow-x-auto rounded-xl border border-border/70">
            <table className={tableClass}>
              <thead><tr><th className={thClass}>Used on</th><th className={thClass}>For</th><th className={thClass}>Amount</th></tr></thead>
              <tbody>
                {data.uses.map((u) => (
                  <tr key={u.id} className={trClass}>
                    <td className={tdClass}>{u.day}<p className="text-xs text-muted-foreground">{u.recorded_by}</p></td>
                    <td className={tdClass}>{u.note}</td>
                    <td className={`${tdClass} font-semibold tabular-nums`}>−{money(u.amount)}</td>
                  </tr>
                ))}
                {data.uses.length === 0 && <tr><td colSpan={3} className="px-4 py-6 text-center text-sm text-muted-foreground">Nothing used yet.</td></tr>}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </Panel>
  );
}
