'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { BsBank, BsCheck2Circle, BsCopy, BsSearch, BsXCircle } from 'react-icons/bs';
import { PayoutsTab } from '@/components/affiliates/payouts-tab';
import {
  Badge, Btn, Drawer, EmptyState, Field, Notice, PageHeader, Panel, Tabs, TextInput, cx, money,
  tableClass, tdClass, thClass, trClass,
} from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost, authedRequest, useApi } from '@/lib/use-api';

interface Context {
  balance: string; deposits: string; paid_out: string; net: string; pending: string; bonus_locked: string;
  big_wins_7d: { amount: string; kind: string; created_at: string }[];
}
interface Withdrawal {
  id: number; player_id: number; username: string; kyc_status: string | null; amount: string; method: string;
  method_label: string; account_number: string; account_name: string; bank_name: string;
  status: 'requested' | 'paid' | 'rejected' | 'cancelled'; status_label: string; reference: string; note: string;
  created_at: string; decided_at: string | null; decided_by: string; context?: Context;
}
interface Queue { results: Withdrawal[]; counts: { requested: number }; pending_total: string }
interface Limits { min_amount: string; max_amount: string; daily_max: string }

const TONE = { requested: 'gold', paid: 'green', rejected: 'red', cancelled: 'slate' } as const;
type Status = Withdrawal['status'] | 'all';

/** Payouts aren't automatic: staff send each one, then record it here. */
export default function WithdrawalsPage() {
  const [tab, setTab] = useState<'players' | 'affiliates' | 'limits'>('players');
  return (
    <div className="space-y-6">
      <PageHeader icon={BsBank} eyebrow="Money" title="Withdrawals & payouts"
        description="Every request to be paid out. Send the money yourself (EcoCash, OneMoney, InnBucks or bank), then mark it paid with the transaction reference — or reject it and the money returns to the balance." />
      <Tabs value={tab} onChange={setTab} items={[
        { id: 'players', label: 'Player withdrawals' }, { id: 'affiliates', label: 'Affiliate payouts' }, { id: 'limits', label: 'Limits' },
      ]} />
      {tab === 'players' ? <PlayerWithdrawals /> : tab === 'affiliates' ? <PayoutsTab /> : <LimitsPanel />}
    </div>
  );
}

function destination(w: Withdrawal) {
  return w.method === 'bank' ? `${w.bank_name} · ${w.account_name} · ${w.account_number}`
    : `${w.account_number}${w.account_name ? ` (${w.account_name})` : ''}`;
}

function PlayerWithdrawals() {
  const { accessToken } = useAuth();
  const [status, setStatus] = useState<Status>('requested');
  const [q, setQ] = useState('');
  const [search, setSearch] = useState('');
  const { data, loading, refetch } = useApi<Queue>(`/admin/withdrawals/?status=${status}${search ? `&q=${encodeURIComponent(search)}` : ''}`);
  const [acting, setActing] = useState<{ w: Withdrawal; verb: 'mark-paid' | 'reject' } | null>(null);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  const list = data?.results ?? [];

  useEffect(() => {
    const t = window.setInterval(refetch, 20000);
    return () => window.clearInterval(t);
  }, [refetch]);

  async function submit() {
    if (!accessToken || !acting) return;
    setBusy(true);
    const body = acting.verb === 'mark-paid' ? { reference: text } : { note: text };
    const res = await authedPost(`/admin/withdrawals/${acting.w.id}/${acting.verb}/`, body, accessToken);
    setBusy(false);
    setNotice(res.error ? { tone: 'red', text: res.error } : {
      tone: 'green',
      text: acting.verb === 'mark-paid' ? `Marked ${money(acting.w.amount)} to ${acting.w.username} as paid — they’ve been notified.`
        : `Rejected — ${money(acting.w.amount)} is back in ${acting.w.username}’s balance.`,
    });
    if (!res.error) setActing(null);
    refetch();
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Tabs value={status} onChange={setStatus} items={[
          { id: 'requested', label: 'To pay', count: status === 'requested' ? list.length : undefined },
          { id: 'paid', label: 'Paid' }, { id: 'rejected', label: 'Rejected' }, { id: 'cancelled', label: 'Cancelled' }, { id: 'all', label: 'All' },
        ]} />
        <form onSubmit={(e) => { e.preventDefault(); setSearch(q.trim()); }} className="ml-auto flex items-center gap-2">
          <TextInput value={q} onChange={(e) => setQ(e.target.value)} placeholder="Player, number or reference" className="w-64" />
          <Btn type="submit" icon={BsSearch}>Search</Btn>
        </form>
      </div>
      {status === 'requested' && data && (
        <p className="text-sm text-muted-foreground">
          <b className="text-foreground">{data.counts.requested}</b> waiting · <b className="text-foreground">{money(data.pending_total)}</b> to send. Oldest first.
        </p>
      )}
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}

      <div className="overflow-hidden rounded-2xl border border-border/70 bg-card">
        {loading && !data ? <div className="h-40 animate-pulse bg-muted/40" />
          : list.length === 0 ? (
            <EmptyState icon={BsCheck2Circle} title={status === 'requested' ? 'No withdrawals waiting' : 'Nothing here'}>
              {status === 'requested' ? 'New requests appear here (and as a count in the menu).' : 'No withdrawals match.'}
            </EmptyState>
          ) : (
            <div className="overflow-x-auto">
              <table className={tableClass}>
                <thead><tr>
                  <th className={thClass}>#</th><th className={thClass}>Player</th><th className={thClass}>Amount</th>
                  <th className={thClass}>Pay to</th>
                  {status === 'requested' && <th className={thClass}>Check before paying</th>}
                  <th className={thClass}>Requested</th><th className={thClass}>Status</th><th className={thClass} />
                </tr></thead>
                <tbody>
                  {list.map((w) => (
                    <tr key={w.id} className={trClass}>
                      <td className={cx(tdClass, 'font-mono text-xs text-muted-foreground')}>W{w.id}</td>
                      <td className={tdClass}>
                        <Link href={`/players/${w.player_id}`} className="font-semibold hover:underline">{w.username}</Link>
                        <p className="text-xs text-muted-foreground">KYC <span className={w.kyc_status === 'verified' ? 'text-win' : 'text-gold'}>{w.kyc_status ?? '—'}</span></p>
                      </td>
                      <td className={cx(tdClass, 'text-base font-extrabold tabular-nums')}>{money(w.amount)}</td>
                      <td className={tdClass}>
                        <p className="font-semibold">{w.method_label}</p>
                        <p className="font-mono text-xs text-muted-foreground">{destination(w)}</p>
                      </td>
                      {status === 'requested' && (
                        <td className={cx(tdClass, 'text-xs')}>
                          {w.context && <ContextCell c={w.context} />}
                        </td>
                      )}
                      <td className={cx(tdClass, 'whitespace-nowrap text-xs text-muted-foreground')}>{new Date(w.created_at).toLocaleString()}</td>
                      <td className={tdClass}>
                        <Badge tone={TONE[w.status]} dot>{w.status_label}</Badge>
                        {(w.reference || w.note) && <p className="mt-1 max-w-[220px] truncate text-xs text-muted-foreground" title={w.note || w.reference}>{w.reference || w.note}</p>}
                        {w.decided_by && <p className="text-[11px] text-muted-foreground">by {w.decided_by}</p>}
                      </td>
                      <td className={cx(tdClass, 'text-right')}>
                        {w.status === 'requested' && (
                          <div className="flex justify-end gap-2">
                            <Btn size="sm" variant="success" icon={BsCheck2Circle} onClick={() => { setActing({ w, verb: 'mark-paid' }); setText(''); }}>Mark paid</Btn>
                            <Btn size="sm" variant="danger" icon={BsXCircle} onClick={() => { setActing({ w, verb: 'reject' }); setText(''); }}>Reject</Btn>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </div>

      <Drawer open={!!acting} onClose={() => setActing(null)}
        title={acting?.verb === 'mark-paid' ? 'Mark withdrawal as paid' : 'Reject withdrawal'}
        description={acting ? `${money(acting.w.amount)} to ${acting.w.username} via ${acting.w.method_label}` : ''}
        footer={<>
          <Btn onClick={() => setActing(null)}>Cancel</Btn>
          <Btn variant={acting?.verb === 'reject' ? 'danger' : 'success'} busy={busy} onClick={submit} disabled={text.trim().length < 3}>
            {acting?.verb === 'mark-paid' ? 'Confirm paid' : 'Reject & return money'}
          </Btn>
        </>}>
        {acting && (
          <div className="space-y-4 text-sm">
            <div className="rounded-xl bg-muted/40 p-3">
              <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Send exactly</p>
              <p className="mt-1 text-2xl font-extrabold tabular-nums">{money(acting.w.amount)}</p>
              <p className="mt-2 text-xs font-bold uppercase tracking-wide text-muted-foreground">To</p>
              <p className="mt-1 flex items-center gap-2 font-mono text-base font-semibold">
                {destination(acting.w)}
                <button aria-label="Copy number" title="Copy number" onClick={() => navigator.clipboard?.writeText(acting.w.account_number)}
                  className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"><BsCopy size={13} /></button>
              </p>
            </div>
            {acting.w.context && <ContextCell c={acting.w.context} wide />}
            {acting.verb === 'mark-paid' ? (
              <>
                <p className="text-muted-foreground">Send the money first, then record it here. The player is notified with the reference.</p>
                <Field label="Transaction reference" hint="The EcoCash/OneMoney/InnBucks or bank confirmation code.">
                  <TextInput value={text} onChange={(e) => setText(e.target.value)} placeholder="MP241011.1530.A12345" />
                </Field>
              </>
            ) : (
              <>
                <p className="text-muted-foreground">The amount goes straight back to the player’s balance and they’re told why.</p>
                <Field label="Reason" hint="Shown to the player.">
                  <TextInput value={text} onChange={(e) => setText(e.target.value)} placeholder="The account name doesn’t match your verified name" />
                </Field>
              </>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
}

function ContextCell({ c, wide }: { c: Context; wide?: boolean }) {
  const net = Number(c.net);
  return (
    <div className={cx('space-y-0.5', wide && 'rounded-xl border border-border p-3')}>
      <p>Deposited <b>{money(c.deposits)}</b> · paid out <b>{money(c.paid_out)}</b></p>
      <p>Net in <b className={net < 0 ? 'text-live' : 'text-win'}>{money(c.net)}</b> · balance {money(c.balance)}</p>
      {Number(c.bonus_locked) > 0 && <p className="text-gold">Bonus locked {money(c.bonus_locked)}</p>}
      {c.big_wins_7d.length > 0 && (
        <p className="text-muted-foreground">Big wins (7d): {c.big_wins_7d.map((w) => money(w.amount)).join(', ')}</p>
      )}
    </div>
  );
}

function LimitsPanel() {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<Limits>('/admin/withdrawal-settings/');
  const [form, setForm] = useState<Limits | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  useEffect(() => { if (data) setForm(data); }, [data]);

  async function save() {
    if (!accessToken || !form) return;
    setBusy(true);
    const res = await authedRequest('PUT', '/admin/withdrawal-settings/', accessToken, form);
    setBusy(false);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: 'Limits saved.' });
    refetch();
  }

  const fields: { key: keyof Limits; label: string; hint: string }[] = [
    { key: 'min_amount', label: 'Minimum per withdrawal ($)', hint: 'Smallest amount a player can ask for.' },
    { key: 'max_amount', label: 'Maximum per withdrawal ($)', hint: 'Largest single request.' },
    { key: 'daily_max', label: 'Daily cap per player ($)', hint: 'Total a player may request per day (0 = no cap).' },
  ];
  return (
    <Panel title="Withdrawal limits" description="Shown to players on their wallet page. Identity verification (KYC) is always required.">
      {notice && <div className="mb-4"><Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice></div>}
      <div className="grid gap-4 sm:grid-cols-3">
        {fields.map((f) => (
          <Field key={f.key} label={f.label} hint={f.hint}>
            <TextInput inputMode="decimal" value={form?.[f.key] ?? ''} onChange={(e) => setForm((v) => v && { ...v, [f.key]: e.target.value.replace(/[^0-9.]/g, '') })} />
          </Field>
        ))}
      </div>
      <div className="mt-4 flex justify-end"><Btn variant="primary" busy={busy} onClick={save}>Save limits</Btn></div>
    </Panel>
  );
}
