'use client';

import { useEffect, useState } from 'react';
import { BsCashCoin, BsPiggyBank, BsPieChart, BsSunrise } from 'react-icons/bs';
import {
  Badge, Btn, EmptyState, Field, Notice, PageHeader, Panel, Select, StatTile, TextInput, cx, money,
  tableClass, tdClass, thClass, trClass,
} from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost, authedRequest, useApi } from '@/lib/use-api';

interface Withdrawal {
  id: number; slot: number; label: string; amount: string; status: 'requested' | 'paid' | 'rejected'; status_label: string;
  method: string; method_label: string; account: string; reference: string; note: string; requested_by: string;
  decided_by: string; created_at: string; decided_at: string | null;
}
interface Wallet {
  slot: number; label: string; holder_id: number | null; holder: string | null; balance: string; earned_total: string;
  paid_total: string; open_withdrawal: Withdrawal | null;
  entries: { kind: string; label: string; amount: string; day: string | null; at: string }[];
}
interface Day {
  day: string; ggr: string; bonus_conversions: string; carried_in: string; base: string; carry_out: string; share_percent: string; share_each: string;
  pool: string; affiliate_costs: string;
}
interface Option { id: string; label: string }
interface HolderView { role: 'holder'; wallet: Wallet; withdrawals: Withdrawal[]; methods: Option[] }
interface BossView {
  role: 'superuser'; own_slot: number | null;
  settings: { share_percent: string; started_on: string | null; locked_start: boolean };
  wallets: Wallet[];
  pool: { earned: string; affiliate_costs: string; expenses: string; remaining: string; expenses_by_category: Record<string, string> };
  today: { day: string; ggr: string; bonus_conversions: string; carried_in: string; base: string; share_each: string; pool: string };
  days: Day[]; withdrawals: Withdrawal[];
  expenses: { id: number; day: string; category: string; category_label: string; amount: string; note: string; recorded_by: string }[];
  categories: Option[]; methods: Option[]; staff: { id: number; username: string }[];
}
type View = HolderView | BossView;

const STATUS_TONE = { requested: 'gold', paid: 'green', rejected: 'red' } as const;
type Tone = { tone: 'green' | 'red'; text: string } | null;

/** The house revenue share: three partner wallets taking a share of each day's GGR, and the operating pool. */
export default function RevenueSharePage() {
  const { data, error, loading, refetch } = useApi<View>('/admin/revenue-share/');
  const [notice, setNotice] = useState<Tone>(null);
  const done = (text: string) => { setNotice({ tone: 'green', text }); refetch(); };
  const fail = (text: string) => setNotice({ tone: 'red', text });

  return (
    <div className="space-y-6">
      <PageHeader icon={BsPieChart} eyebrow="Money" title="Revenue share"
        description="Each day’s real-money GGR is shared when the day ends: cash stakes minus cash wins (sports and Aviator). Bonus money doesn’t count until a player unlocks it into Winnings — then it’s deducted that day. Three partner wallets take their share each, and the operating pool keeps the rest to pay affiliates and running costs. A losing day is carried forward and earned back before anything is shared." />
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}
      {error && (
        <Notice tone="red">
          {error.includes('403') ? 'Revenue share is visible to superusers and the three wallet holders only.' : error}
        </Notice>
      )}
      {loading && !data && <div className="h-48 animate-pulse rounded-2xl bg-muted/40" />}
      {data?.role === 'holder' && <HolderPanel view={data} onDone={done} onFail={fail} />}
      {data?.role === 'superuser' && <BossPanel view={data} onDone={done} onFail={fail} />}
    </div>
  );
}

function WithdrawForm({ wallet, methods, onDone, onFail }: {
  wallet: Wallet; methods: Option[]; onDone: (t: string) => void; onFail: (t: string) => void;
}) {
  const { accessToken } = useAuth();
  const [method, setMethod] = useState(methods[0]?.id ?? 'ecocash');
  const [account, setAccount] = useState('');
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  if (wallet.open_withdrawal) {
    return <p className="text-sm text-muted-foreground">Your withdrawal of {money(wallet.open_withdrawal.amount)} to {wallet.open_withdrawal.method_label} is waiting to be paid.</p>;
  }
  if (Number(wallet.balance) < 0.01) return <p className="text-sm text-muted-foreground">Nothing to withdraw yet — your share is added when each day ends.</p>;
  async function send() {
    if (!accessToken) return;
    setBusy(true);
    const res = await authedPost('/admin/revenue-share/withdraw/', { method, account }, accessToken);
    setBusy(false); setConfirming(false);
    if (res.error) onFail(res.error); else { setAccount(''); onDone(`Withdrawal of ${money(wallet.balance)} requested. Your wallet starts again from $0.00.`); }
  }
  return (
    <div className="flex flex-wrap items-end gap-3">
      <Field label="Pay me by" className="min-w-[160px]">
        <Select value={method} onChange={(e) => setMethod(e.target.value)}>
          {methods.map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
        </Select>
      </Field>
      {method !== 'cash' && (
        <Field label={method === 'bank' ? 'Bank, account name and number' : 'Mobile number'} className="min-w-[220px] flex-1">
          <TextInput value={account} onChange={(e) => setAccount(e.target.value)} placeholder={method === 'bank' ? 'Steward Bank · J Moyo · 1002345678' : '0771234567'} />
        </Field>
      )}
      {confirming && <Btn variant="ghost" onClick={() => setConfirming(false)}>Cancel</Btn>}
      <Btn variant="primary" busy={busy} disabled={method !== 'cash' && account.trim().length < 5}
        onClick={() => (confirming ? send() : setConfirming(true))}>
        {confirming ? `Confirm: withdraw ${money(wallet.balance)}` : `Withdraw ${money(wallet.balance)}…`}
      </Btn>
    </div>
  );
}

function WalletCard({ w, children }: { w: Wallet; children?: React.ReactNode }) {
  return (
    <div className="rounded-2xl border border-border/70 bg-card p-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-[11.5px] font-bold uppercase tracking-wide text-muted-foreground">{w.label}</p>
          <p className="text-xs text-muted-foreground">{w.holder ? `Held by ${w.holder}` : 'No holder yet — still accruing'}</p>
        </div>
        {w.open_withdrawal && <Badge tone="gold" dot>Withdrawal requested</Badge>}
      </div>
      <p className="mt-2 text-[28px] font-extrabold tabular-nums">{money(w.balance)}</p>
      <p className="text-xs text-muted-foreground">Earned {money(w.earned_total)} · paid out {money(w.paid_total)}</p>
      {children && <div className="mt-3 border-t border-border/60 pt-3">{children}</div>}
    </div>
  );
}

function WithdrawalsTable({ rows, decide }: { rows: Withdrawal[]; decide?: (w: Withdrawal) => React.ReactNode }) {
  if (rows.length === 0) return <EmptyState icon={BsCashCoin} title="No withdrawals yet" />;
  return (
    <div className="overflow-x-auto">
      <table className={tableClass}>
        <thead><tr>
          <th className={thClass}>Wallet</th><th className={thClass}>Amount</th><th className={thClass}>To</th>
          <th className={thClass}>Status</th><th className={thClass}>Requested</th>{decide && <th className={thClass} />}
        </tr></thead>
        <tbody>
          {rows.map((w) => (
            <tr key={w.id} className={trClass}>
              <td className={tdClass}>{w.label}<p className="text-xs text-muted-foreground">{w.requested_by}</p></td>
              <td className={cx(tdClass, 'font-semibold tabular-nums')}>{money(w.amount)}</td>
              <td className={cx(tdClass, 'text-xs')}>{w.method_label}{w.account && <p className="text-muted-foreground">{w.account}</p>}</td>
              <td className={tdClass}>
                <Badge tone={STATUS_TONE[w.status]} dot>{w.status_label}</Badge>
                {(w.reference || w.note) && <p className="mt-1 text-xs text-muted-foreground">{[w.reference, w.note].filter(Boolean).join(' · ')}</p>}
              </td>
              <td className={cx(tdClass, 'whitespace-nowrap text-xs text-muted-foreground')}>{new Date(w.created_at).toLocaleString()}</td>
              {decide && <td className={tdClass}>{w.status === 'requested' && decide(w)}</td>}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function HolderPanel({ view, onDone, onFail }: { view: HolderView; onDone: (t: string) => void; onFail: (t: string) => void }) {
  const w = view.wallet;
  return (
    <>
      <WalletCard w={w}><WithdrawForm wallet={w} methods={view.methods} onDone={onDone} onFail={onFail} /></WalletCard>
      <Panel title="My wallet’s history" padded={false}>
        {w.entries.length === 0 ? <EmptyState icon={BsPiggyBank} title="Nothing yet" /> : (
          <table className={tableClass}>
            <tbody>
              {w.entries.map((e, i) => (
                <tr key={i} className={trClass}>
                  <td className={tdClass}>{e.label}{e.day && <span className="ml-2 text-xs text-muted-foreground">{e.day}</span>}</td>
                  <td className={cx(tdClass, 'text-right font-semibold tabular-nums', Number(e.amount) < 0 ? 'text-live' : 'text-win')}>{money(e.amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </Panel>
      <Panel title="My withdrawals" padded={false}><WithdrawalsTable rows={view.withdrawals} /></Panel>
    </>
  );
}

function Decide({ w, onDone, onFail }: { w: Withdrawal; onDone: (t: string) => void; onFail: (t: string) => void }) {
  const { accessToken } = useAuth();
  const [reference, setReference] = useState('');
  const [busy, setBusy] = useState(false);
  async function decide(decision: 'paid' | 'rejected') {
    if (!accessToken) return;
    if (decision === 'rejected' && !window.confirm(`Reject this withdrawal? ${money(w.amount)} goes back into ${w.label}’s wallet.`)) return;
    setBusy(true);
    const res = await authedPost(`/admin/revenue-share/withdrawals/${w.id}/decide/`, { decision, reference }, accessToken);
    setBusy(false);
    if (res.error) onFail(res.error); else onDone(decision === 'paid' ? `${money(w.amount)} to ${w.label} recorded as paid.` : `Withdrawal rejected — ${money(w.amount)} is back in ${w.label}’s wallet.`);
  }
  return (
    <div className="flex flex-wrap items-center gap-2">
      <TextInput value={reference} onChange={(e) => setReference(e.target.value)} placeholder="Transaction ref" className="h-8 w-36 text-xs" />
      <Btn size="sm" variant="success" busy={busy} onClick={() => decide('paid')}>Mark paid</Btn>
      <Btn size="sm" variant="danger" busy={busy} onClick={() => decide('rejected')}>Reject</Btn>
    </div>
  );
}

function BossPanel({ view, onDone, onFail }: { view: BossView; onDone: (t: string) => void; onFail: (t: string) => void }) {
  const pct = Number(view.settings.share_percent);
  const own = view.wallets.find((w) => w.slot === view.own_slot);
  return (
    <>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile label="Today so far (real-money GGR)" value={money(view.today.ggr)} icon={BsSunrise}
          hint={`${Number(view.today.bonus_conversions) > 0 ? `After ${money(view.today.bonus_conversions)} of bonus unlocked into Winnings. ` : ''}If the day ended now: ${money(view.today.share_each)} per wallet, ${money(view.today.pool)} to the pool${Number(view.today.carried_in) < 0 ? ` (after ${money(view.today.carried_in)} carried from losing days)` : ''}.`} />
        <StatTile label="Operating pool left" value={money(view.pool.remaining)} icon={BsPiggyBank} tone={Number(view.pool.remaining) < 0 ? 'red' : 'indigo'}
          hint={`${money(view.pool.earned)} in, less ${money(view.pool.affiliate_costs)} affiliates and ${money(view.pool.expenses)} costs.`} />
        <StatTile label="Share per wallet" value={`${pct}%`} icon={BsPieChart} hint={`Pool keeps ${(100 - 3 * pct).toFixed(2).replace(/\.00$/, '')}% of each day.`} />
        <StatTile label="Owed to partners" value={money(view.wallets.reduce((s, w) => s + Number(w.balance), 0))} icon={BsCashCoin}
          hint="Across the three wallets, not yet withdrawn." />
      </div>

      <div className="grid gap-3 lg:grid-cols-3">
        {view.wallets.map((w) => (
          <WalletCard key={w.slot} w={w}>
            {w.slot === view.own_slot
              ? <WithdrawForm wallet={w} methods={view.methods} onDone={onDone} onFail={onFail} />
              : <p className="text-xs text-muted-foreground">Resets to $0.00 when {w.holder ?? 'its holder'} asks for a withdrawal.</p>}
          </WalletCard>
        ))}
      </div>
      {!own && <p className="text-xs text-muted-foreground">You don’t hold a wallet yourself; holders request their own withdrawals and you mark them paid below.</p>}

      <Panel title="Withdrawals" description="Send the money, then mark it paid with the transaction reference. Rejecting puts the amount back in that wallet." padded={false}>
        <WithdrawalsTable rows={view.withdrawals} decide={(w) => <Decide w={w} onDone={onDone} onFail={onFail} />} />
      </Panel>

      <PoolPanel view={view} onDone={onDone} onFail={onFail} />

      <Panel title="Closed days" description="Each day is shared once, when it ends. A losing day carries its loss forward; later days earn it back before anything is shared." padded={false}>
        {view.days.length === 0 ? <EmptyState icon={BsSunrise} title="No days closed yet">The first day is shared when it ends.</EmptyState> : (
          <div className="overflow-x-auto">
            <table className={tableClass}>
              <thead><tr>
                <th className={thClass}>Day</th><th className={thClass}>Real-money GGR</th><th className={thClass}>Bonus unlocked</th><th className={thClass}>Carried in</th>
                <th className={thClass}>Shared</th><th className={thClass}>Each wallet</th><th className={thClass}>Pool</th>
                <th className={thClass}>Affiliates</th><th className={thClass}>Carried out</th>
              </tr></thead>
              <tbody>
                {view.days.map((d) => (
                  <tr key={d.day} className={trClass}>
                    <td className={cx(tdClass, 'whitespace-nowrap font-medium')}>{d.day}</td>
                    <td className={cx(tdClass, 'tabular-nums', Number(d.ggr) < 0 && 'text-live')}>{money(d.ggr)}</td>
                    <td className={cx(tdClass, 'tabular-nums text-muted-foreground')}>{Number(d.bonus_conversions) > 0 ? money(-Number(d.bonus_conversions)) : '—'}</td>
                    <td className={cx(tdClass, 'tabular-nums text-muted-foreground')}>{Number(d.carried_in) < 0 ? money(d.carried_in) : '—'}</td>
                    <td className={cx(tdClass, 'tabular-nums')}>{money(d.base)}</td>
                    <td className={cx(tdClass, 'tabular-nums font-semibold')}>{money(d.share_each)} <span className="text-xs font-normal text-muted-foreground">({Number(d.share_percent)}%)</span></td>
                    <td className={cx(tdClass, 'tabular-nums')}>{money(d.pool)}</td>
                    <td className={cx(tdClass, 'tabular-nums text-muted-foreground')}>{money(d.affiliate_costs)}</td>
                    <td className={cx(tdClass, 'tabular-nums text-muted-foreground')}>{Number(d.carry_out) < 0 ? money(d.carry_out) : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <SettingsPanel view={view} onDone={onDone} onFail={onFail} />
    </>
  );
}

function PoolPanel({ view, onDone, onFail }: { view: BossView; onDone: (t: string) => void; onFail: (t: string) => void }) {
  const { accessToken } = useAuth();
  const today = view.today.day;
  const [form, setForm] = useState({ day: today, category: view.categories[0]?.id ?? 'ai', amount: '', note: '' });
  const [busy, setBusy] = useState(false);
  async function add() {
    if (!accessToken) return;
    setBusy(true);
    const res = await authedPost('/admin/revenue-share/expenses/', form, accessToken);
    setBusy(false);
    if (res.error) onFail(res.error); else { setForm((f) => ({ ...f, amount: '', note: '' })); onDone('Cost recorded against the operating pool.'); }
  }
  async function remove(id: number) {
    if (!accessToken || !window.confirm('Delete this cost?')) return;
    const res = await authedRequest('DELETE', `/admin/revenue-share/expenses/${id}/`, accessToken);
    if (res.error) onFail(res.error); else onDone('Cost deleted.');
  }
  return (
    <Panel title="Operating pool" description={`The ${(100 - 3 * Number(view.settings.share_percent)).toFixed(2).replace(/\.00$/, '')}% of each day that isn’t shared. Affiliate commissions are taken from it automatically; record every other cost (Claude, hosting, SMS…) here.`}>
      <div className="mb-4 grid gap-3 sm:grid-cols-4">
        <Mini label="Into the pool" value={view.pool.earned} />
        <Mini label="Affiliates paid" value={`-${view.pool.affiliate_costs}`} />
        <Mini label="Costs recorded" value={`-${view.pool.expenses}`} />
        <Mini label="Left" value={view.pool.remaining} strong />
      </div>
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Date" className="w-40"><TextInput type="date" value={form.day} max={today} onChange={(e) => setForm({ ...form, day: e.target.value })} /></Field>
        <Field label="Cost" className="min-w-[180px]">
          <Select value={form.category} onChange={(e) => setForm({ ...form, category: e.target.value })}>
            {view.categories.map((c) => <option key={c.id} value={c.id}>{c.label}</option>)}
          </Select>
        </Field>
        <Field label="Amount ($)" className="w-32"><TextInput inputMode="decimal" value={form.amount} onChange={(e) => setForm({ ...form, amount: e.target.value.replace(/[^0-9.]/g, '') })} /></Field>
        <Field label="Note" className="min-w-[200px] flex-1"><TextInput value={form.note} onChange={(e) => setForm({ ...form, note: e.target.value })} placeholder="Claude, November" /></Field>
        <Btn variant="primary" busy={busy} disabled={!(Number(form.amount) > 0)} onClick={add}>Record cost</Btn>
      </div>
      {view.expenses.length > 0 && (
        <table className={cx(tableClass, 'mt-4')}>
          <tbody>
            {view.expenses.map((e) => (
              <tr key={e.id} className={trClass}>
                <td className={cx(tdClass, 'whitespace-nowrap text-xs')}>{e.day}</td>
                <td className={tdClass}>{e.category_label}{e.note && <span className="ml-2 text-xs text-muted-foreground">{e.note}</span>}</td>
                <td className={cx(tdClass, 'text-xs text-muted-foreground')}>{e.recorded_by}</td>
                <td className={cx(tdClass, 'text-right font-semibold tabular-nums')}>{money(e.amount)}</td>
                <td className={cx(tdClass, 'w-16 text-right')}><button onClick={() => remove(e.id)} className="text-xs font-semibold text-live hover:underline">Delete</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </Panel>
  );
}

function Mini({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="rounded-xl bg-muted/50 p-3">
      <p className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cx('mt-0.5 tabular-nums', strong ? 'text-xl font-extrabold' : 'font-semibold', Number(value) < 0 && strong && 'text-live')}>{money(value)}</p>
    </div>
  );
}

function SettingsPanel({ view, onDone, onFail }: { view: BossView; onDone: (t: string) => void; onFail: (t: string) => void }) {
  const { accessToken } = useAuth();
  const [pct, setPct] = useState(view.settings.share_percent);
  const [start, setStart] = useState(view.settings.started_on ?? '');
  const [rows, setRows] = useState(view.wallets.map((w) => ({ slot: w.slot, label: w.label, holder_id: w.holder_id ? String(w.holder_id) : '' })));
  const [busy, setBusy] = useState(false);
  useEffect(() => {
    setPct(view.settings.share_percent); setStart(view.settings.started_on ?? '');
    setRows(view.wallets.map((w) => ({ slot: w.slot, label: w.label, holder_id: w.holder_id ? String(w.holder_id) : '' })));
  }, [view]);
  async function save() {
    if (!accessToken) return;
    setBusy(true);
    const res = await authedRequest('PUT', '/admin/revenue-share/settings/', accessToken, {
      share_percent: pct, started_on: start || null,
      wallets: rows.map((r) => ({ slot: r.slot, label: r.label, holder_id: r.holder_id ? Number(r.holder_id) : null })),
    });
    setBusy(false);
    if (res.error) onFail(res.error); else onDone('Revenue-share settings saved.');
  }
  return (
    <Panel title="Settings" description="Who holds each wallet (a staff login; they see only their own wallet and ask for its withdrawal), each wallet’s share, and the first day that counts.">
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Field label="Share per wallet (%)" hint="Applies to days not yet closed. Three wallets, so at most 33.33%.">
          <TextInput inputMode="decimal" value={pct} onChange={(e) => setPct(e.target.value.replace(/[^0-9.]/g, ''))} />
        </Field>
        <Field label="First day that counts" hint={view.settings.locked_start ? 'Fixed once a day has been shared.' : 'Days before it are never shared.'}>
          <TextInput type="date" value={start} disabled={view.settings.locked_start} onChange={(e) => setStart(e.target.value)} />
        </Field>
      </div>
      <div className="mt-4 grid gap-4 lg:grid-cols-3">
        {rows.map((r, i) => (
          <div key={r.slot} className="space-y-2 rounded-xl border border-border/60 p-3">
            <Field label={`Wallet ${r.slot} name`}>
              <TextInput value={r.label} onChange={(e) => setRows((x) => x.map((y, j) => (j === i ? { ...y, label: e.target.value } : y)))} />
            </Field>
            <Field label="Held by">
              <Select value={r.holder_id} onChange={(e) => setRows((x) => x.map((y, j) => (j === i ? { ...y, holder_id: e.target.value } : y)))}>
                <option value="">Nobody yet</option>
                {view.staff.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
              </Select>
            </Field>
          </div>
        ))}
      </div>
      <div className="mt-4 flex justify-end"><Btn variant="primary" busy={busy} onClick={save}>Save settings</Btn></div>
    </Panel>
  );
}
