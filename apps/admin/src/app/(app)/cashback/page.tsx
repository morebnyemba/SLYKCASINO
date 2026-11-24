'use client';

import { useEffect, useState } from 'react';
import { BsArrowCounterclockwise } from 'react-icons/bs';
import { Badge, Btn, Field, Notice, PageHeader, Panel, Switch, TextInput } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';

interface Tier { id?: number; name: string; min_loss: string; percent: string; max_amount: string; min_tickets: number; min_active_days: number; active: boolean }
interface Data {
  can_edit: boolean;
  refund: { enabled: boolean; min_odds: string; divisor: string; max_refund: string; paid_count: number; paid_total: string };
  cashback: { enabled: boolean; period_days: number; starts_on: string; last_period_start: string | null; paid_count: number; paid_total: string };
  tiers: Tier[];
  recent: { player: string; period: string; loss: string; percent: string; amount: string; created_at: string }[];
}

const money = (v: string | number) => `$${Number(v).toFixed(2)}`;
const blankTier: Tier = { name: '', min_loss: '50', percent: '5', max_amount: '', min_tickets: 0, min_active_days: 0, active: true };

/** Lost-by-one refunds and cashback on losses: both paid to the Winnings wallet. */
export default function CashbackPage() {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<Data>('/admin/cashback/');
  const [form, setForm] = useState<Data | null>(null);
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  useEffect(() => { if (data) setForm(data); }, [data]);
  const edit = !!data?.can_edit;

  async function save(part: 'refund' | 'cashback', body: object) {
    if (!accessToken) return;
    setBusy(part); setNotice(null);
    const res = await authedRequest<Data>('PUT', '/admin/cashback/', accessToken, body);
    setBusy('');
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: 'Saved.' });
    if (!res.error) refetch();
  }

  if (!form) return <PageHeader icon={BsArrowCounterclockwise} eyebrow="Promotions & bonuses" title="Cashback & refunds" description="Loading…" />;
  const r = form.refund;
  const c = form.cashback;
  const setR = (k: keyof Data['refund'], v: string | boolean) => setForm({ ...form, refund: { ...r, [k]: v } });
  const setC = (k: keyof Data['cashback'], v: string | number | boolean) => setForm({ ...form, cashback: { ...c, [k]: v } });
  const setTier = (i: number, k: keyof Tier, v: string | number | boolean) =>
    setForm({ ...form, tiers: form.tiers.map((t, j) => (j === i ? { ...t, [k]: v } : t)) });
  const ex = Number(r.divisor) > 0 ? (1 * 100 / Number(r.divisor) / 2) : 0;

  return (
    <div className="space-y-6">
      <PageHeader icon={BsArrowCounterclockwise} eyebrow="Promotions & bonuses" title="Cashback & refunds"
        description="Money back to players, paid automatically to the Winnings wallet. Bonus-wallet play never counts." />
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}
      {!edit && <Notice tone="red">Only a superuser can change these rules.</Notice>}

      <Panel title="Lost by one: refund"
        description="A multiple that lost on exactly one match, with ticket odds above the minimum, gets back: stake × ticket odds ÷ “divide by” ÷ the lost match’s odds. Paid once every match on it has a result."
        actions={<Badge tone={r.enabled ? 'green' : 'slate'} dot>{r.enabled ? 'On' : 'Off'}</Badge>}>
        <div className="space-y-5">
          <span className="flex items-center gap-2 text-sm font-semibold">
            <Switch checked={r.enabled} disabled={!edit} onChange={(v) => setR('enabled', v)} label="Refunds on" /> Refunds on
          </span>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Ticket odds above"><TextInput inputMode="decimal" value={r.min_odds} disabled={!edit} onChange={(e) => setR('min_odds', e.target.value)} /></Field>
            <Field label="Divide by"><TextInput inputMode="decimal" value={r.divisor} disabled={!edit} onChange={(e) => setR('divisor', e.target.value)} /></Field>
            <Field label="Most per refund ($)" hint="Blank = no limit."><TextInput inputMode="decimal" value={r.max_refund} disabled={!edit} onChange={(e) => setR('max_refund', e.target.value)} /></Field>
          </div>
          <p className="text-xs text-muted-foreground">Example: $1 at odds 100 that lost on a 2.00 → 1 × 100 ÷ {r.divisor || '…'} ÷ 2 = <b>{money(ex)}</b>. Paid so far: {r.paid_count} refunds, {money(r.paid_total)}.</p>
          {edit && <Btn variant="primary" busy={busy === 'refund'} onClick={() => save('refund', { refund: r })}>Save</Btn>}
        </div>
      </Panel>

      <Panel title="Cashback on losses"
        description="At the end of each period, each player gets the best tier they meet: that % of their real-money losses in the period (sports and Aviator), up to the tier’s limit."
        actions={<Badge tone={c.enabled ? 'green' : 'slate'} dot>{c.enabled ? 'On' : 'Off'}</Badge>}>
        <div className="space-y-5">
          <span className="flex items-center gap-2 text-sm font-semibold">
            <Switch checked={c.enabled} disabled={!edit} onChange={(v) => setC('enabled', v)} label="Cashback on" /> Cashback on
          </span>
          <div className="grid gap-4 sm:grid-cols-2">
            <Field label="Period (days)" hint="7 = weekly."><TextInput inputMode="numeric" value={String(c.period_days)} disabled={!edit} onChange={(e) => setC('period_days', Number(e.target.value.replace(/\D/g, '') || 0))} /></Field>
            <Field label="First period starts"><TextInput type="date" value={c.starts_on} disabled={!edit} onChange={(e) => setC('starts_on', e.target.value)} /></Field>
          </div>

          <div className="space-y-2">
            <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Tiers</p>
            {form.tiers.map((t, i) => (
              <div key={t.id ?? `n${i}`} className="grid items-end gap-2 rounded-xl border border-border/70 p-3 sm:grid-cols-7">
                <Field label="Name"><TextInput value={t.name} disabled={!edit} onChange={(e) => setTier(i, 'name', e.target.value)} placeholder="Silver" /></Field>
                <Field label="Lost at least ($)"><TextInput inputMode="decimal" value={t.min_loss} disabled={!edit} onChange={(e) => setTier(i, 'min_loss', e.target.value)} /></Field>
                <Field label="Cashback %"><TextInput inputMode="decimal" value={t.percent} disabled={!edit} onChange={(e) => setTier(i, 'percent', e.target.value)} /></Field>
                <Field label="Most ($)"><TextInput inputMode="decimal" value={t.max_amount} disabled={!edit} onChange={(e) => setTier(i, 'max_amount', e.target.value)} placeholder="no limit" /></Field>
                <Field label="Tickets at least"><TextInput inputMode="numeric" value={String(t.min_tickets)} disabled={!edit} onChange={(e) => setTier(i, 'min_tickets', Number(e.target.value.replace(/\D/g, '') || 0))} /></Field>
                <Field label="Days played at least"><TextInput inputMode="numeric" value={String(t.min_active_days)} disabled={!edit} onChange={(e) => setTier(i, 'min_active_days', Number(e.target.value.replace(/\D/g, '') || 0))} /></Field>
                <div className="flex items-center gap-2 pb-2">
                  <Switch checked={t.active} disabled={!edit} onChange={(v) => setTier(i, 'active', v)} label="Active" />
                  {edit && <Btn size="sm" onClick={() => setForm({ ...form, tiers: form.tiers.filter((_, j) => j !== i) })}>Remove</Btn>}
                </div>
              </div>
            ))}
            {edit && <Btn size="sm" onClick={() => setForm({ ...form, tiers: [...form.tiers, { ...blankTier }] })}>+ Add tier</Btn>}
          </div>
          <p className="text-xs text-muted-foreground">
            Paid so far: {c.paid_count} cashbacks, {money(c.paid_total)}.{c.last_period_start ? ` Last period paid: from ${c.last_period_start}.` : ''}
          </p>
          {edit && <Btn variant="primary" busy={busy === 'cashback'} onClick={() => save('cashback', { cashback: c, tiers: form.tiers })}>Save cashback</Btn>}
        </div>
      </Panel>

      <Panel title="Recent cashback">
        {!form.recent.length ? <p className="text-sm text-muted-foreground">None paid yet.</p> : (
          <ul className="divide-y divide-border/70 text-sm">
            {form.recent.map((p, i) => (
              <li key={i} className="flex flex-wrap justify-between gap-2 py-2">
                <span><b>{p.player}</b> <span className="text-xs text-muted-foreground">{p.period}</span></span>
                <span className="tabular-nums">lost {money(p.loss)} · {Number(p.percent)}% → <b>{money(p.amount)}</b></span>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
