'use client';

import { useState } from 'react';
import { BsPencil, BsPlusLg, BsTrash } from 'react-icons/bs';
import { Badge, Btn, Drawer, EmptyState, Field, Notice, Panel, Select, Switch, TextInput, money } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';

type Limit = 'every' | 'daily' | 'once';
interface Tier {
  id: number; name: string; active: boolean;
  min_deposit: string; max_deposit: string | null; percent: string; max_bonus: string;
  wagering_multiplier: string; limit: Limit; starts_at: string | null; ends_at: string | null;
  given: number; total_given: string;
}

const LIMITS: { id: Limit; label: string }[] = [
  { id: 'every', label: 'Every deposit' }, { id: 'daily', label: 'Once a day per player' }, { id: 'once', label: 'Once per player' },
];
const BLANK = { name: '', active: true, min_deposit: '', max_deposit: '', percent: '', max_bonus: '0', wagering_multiplier: '5', limit: 'every' as Limit, starts_at: '', ends_at: '' };
type Form = typeof BLANK;

const toLocal = (iso: string | null) => (iso ? new Date(iso).toISOString().slice(0, 16) : '');
const range = (t: Pick<Tier, 'min_deposit' | 'max_deposit'>) =>
  t.max_deposit ? `${money(t.min_deposit)} – ${money(t.max_deposit)}` : `${money(t.min_deposit)} and above`;

function example(f: Form) {
  const pct = Number(f.percent), low = Number(f.min_deposit);
  if (!(pct > 0) || !(low >= 0)) return null;
  const amount = Math.max(low, f.max_deposit ? Math.min(Number(f.max_deposit), low * 2 || 50) : low * 2 || 50);
  let bonus = (amount * pct) / 100;
  const cap = Number(f.max_bonus);
  if (cap > 0) bonus = Math.min(bonus, cap);
  const wager = bonus * Number(f.wagering_multiplier || 0);
  return `A ${money(amount)} deposit gets ${money(bonus)} bonus${wager > 0 ? `, withdrawable after betting ${money(wager)}` : ''}.`;
}

/** Deposit promotions: a % of the deposit depending on how much is deposited. */
export function DepositBonuses() {
  const { accessToken } = useAuth();
  const { data, loading, refetch } = useApi<Tier[]>('/admin/deposit-bonuses/');
  const [editing, setEditing] = useState<number | 'new' | null>(null);
  const [form, setForm] = useState<Form>(BLANK);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const tiers = Array.isArray(data) ? data : [];

  function open(t?: Tier) {
    setError('');
    setEditing(t ? t.id : 'new');
    setForm(t ? {
      name: t.name, active: t.active, min_deposit: t.min_deposit, max_deposit: t.max_deposit ?? '', percent: t.percent,
      max_bonus: t.max_bonus, wagering_multiplier: t.wagering_multiplier, limit: t.limit,
      starts_at: toLocal(t.starts_at), ends_at: toLocal(t.ends_at),
    } : BLANK);
  }

  async function save() {
    if (!accessToken || editing == null) return;
    setBusy(true); setError('');
    const body = {
      ...form,
      max_deposit: form.max_deposit === '' ? null : form.max_deposit,
      max_bonus: form.max_bonus === '' ? '0' : form.max_bonus,
      starts_at: form.starts_at ? new Date(form.starts_at).toISOString() : null,
      ends_at: form.ends_at ? new Date(form.ends_at).toISOString() : null,
    };
    const res = editing === 'new'
      ? await authedRequest('POST', '/admin/deposit-bonuses/', accessToken, body)
      : await authedRequest('PATCH', `/admin/deposit-bonuses/${editing}/`, accessToken, body);
    setBusy(false);
    if (res.error) {
      setError(res.fields ? Object.entries(res.fields).map(([k, v]) => `${k.replace(/_/g, ' ')}: ${v.join(' ')}`).join(' · ') : res.error);
      return;
    }
    setNotice(editing === 'new' ? `“${form.name}” is live.` : `“${form.name}” saved.`);
    setEditing(null);
    refetch();
  }

  async function toggle(t: Tier) {
    if (!accessToken) return;
    await authedRequest('PATCH', `/admin/deposit-bonuses/${t.id}/`, accessToken, { active: !t.active });
    refetch();
  }

  async function remove(t: Tier) {
    if (!accessToken || !window.confirm(`Delete “${t.name}”? Bonuses it already gave stay with the players.`)) return;
    await authedRequest('DELETE', `/admin/deposit-bonuses/${t.id}/`, accessToken);
    refetch();
  }

  const set = <K extends keyof Form>(k: K, v: Form[K]) => setForm((f) => ({ ...f, [k]: v }));
  const preview = example(form);

  return (
    <Panel
      title="Deposit bonuses"
      description="Give players a percentage of what they deposit, depending on the amount. The bonus is added automatically on the deposit and must be bet through before it can be withdrawn. One bonus per deposit: the biggest that applies."
      actions={<Btn variant="primary" size="sm" icon={BsPlusLg} onClick={() => open()}>Add tier</Btn>}
      padded={false}
    >
      {notice && <div className="px-5 pt-4"><Notice onClose={() => setNotice('')}>{notice}</Notice></div>}
      {loading && !data ? (
        <div className="m-5 h-24 animate-pulse rounded-xl bg-muted/50" />
      ) : tiers.length === 0 ? (
        <div className="p-5">
          <EmptyState title="No deposit bonuses yet" action={<Btn variant="primary" size="sm" icon={BsPlusLg} onClick={() => open()}>Add the first tier</Btn>}>
            For example: $10–$49 gets 10%, $50 and above gets 25% (up to $100).
          </EmptyState>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-[760px] text-sm">
            <thead className="text-left text-xs text-muted-foreground">
              <tr className="border-b border-border">
                <th className="px-5 py-2.5 font-medium">Tier</th>
                <th className="px-3 py-2.5 font-medium">Deposit</th>
                <th className="px-3 py-2.5 font-medium">Bonus</th>
                <th className="px-3 py-2.5 font-medium">Bet through</th>
                <th className="px-3 py-2.5 font-medium">Limit</th>
                <th className="px-3 py-2.5 text-right font-medium">Given</th>
                <th className="px-3 py-2.5 font-medium">On</th>
                <th className="px-5 py-2.5" />
              </tr>
            </thead>
            <tbody>
              {tiers.map((t) => {
                const ended = t.ends_at && new Date(t.ends_at) < new Date();
                const upcoming = t.starts_at && new Date(t.starts_at) > new Date();
                return (
                  <tr key={t.id} className="border-b border-border/60 last:border-0">
                    <td className="px-5 py-3">
                      <p className="font-semibold">{t.name}</p>
                      {(ended || upcoming) && <Badge tone={ended ? 'slate' : 'gold'}>{ended ? 'Ended' : `Starts ${new Date(t.starts_at!).toLocaleDateString()}`}</Badge>}
                      {!ended && !upcoming && t.ends_at && <p className="text-xs text-muted-foreground">Until {new Date(t.ends_at).toLocaleString()}</p>}
                    </td>
                    <td className="px-3 py-3 tabular-nums">{range(t)}</td>
                    <td className="px-3 py-3 font-bold tabular-nums text-win">
                      {Number(t.percent)}%{Number(t.max_bonus) > 0 && <span className="ml-1 text-xs font-normal text-muted-foreground">up to {money(t.max_bonus)}</span>}
                    </td>
                    <td className="px-3 py-3 tabular-nums">{Number(t.wagering_multiplier) > 0 ? `${Number(t.wagering_multiplier)}× the bonus` : 'Not needed'}</td>
                    <td className="px-3 py-3 text-xs">{LIMITS.find((l) => l.id === t.limit)?.label}</td>
                    <td className="px-3 py-3 text-right tabular-nums">{t.given}<span className="block text-xs text-muted-foreground">{money(t.total_given)}</span></td>
                    <td className="px-3 py-3"><Switch checked={t.active} onChange={() => void toggle(t)} label={`${t.name} on`} /></td>
                    <td className="px-5 py-3">
                      <div className="flex justify-end gap-1.5">
                        <Btn size="sm" icon={BsPencil} onClick={() => open(t)}>Edit</Btn>
                        <Btn size="sm" variant="danger" icon={BsTrash} onClick={() => void remove(t)} aria-label={`Delete ${t.name}`} />
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <Drawer
        open={editing != null}
        onClose={() => setEditing(null)}
        title={editing === 'new' ? 'New deposit bonus' : 'Edit deposit bonus'}
        description="Pick the deposit range and the percentage it earns."
        footer={<>
          <Btn variant="ghost" onClick={() => setEditing(null)}>Cancel</Btn>
          <Btn variant="primary" busy={busy} disabled={!form.name.trim() || form.min_deposit === '' || form.percent === ''} onClick={() => void save()}>
            {editing === 'new' ? 'Create' : 'Save'}
          </Btn>
        </>}
      >
        <div className="space-y-4">
          <Field label="Name" hint="Players see this, e.g. “Gold deposit bonus”.">
            <TextInput value={form.name} maxLength={80} onChange={(e) => set('name', e.target.value)} />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="Deposit from ($)"><TextInput type="number" min="0" step="0.01" value={form.min_deposit} onChange={(e) => set('min_deposit', e.target.value)} /></Field>
            <Field label="Up to ($)" hint="Empty = no upper limit"><TextInput type="number" min="0" step="0.01" value={form.max_deposit} onChange={(e) => set('max_deposit', e.target.value)} /></Field>
            <Field label="Bonus (%)"><TextInput type="number" min="0" max="500" step="0.01" value={form.percent} onChange={(e) => set('percent', e.target.value)} /></Field>
            <Field label="Biggest bonus ($)" hint="0 = no cap"><TextInput type="number" min="0" step="0.01" value={form.max_bonus} onChange={(e) => set('max_bonus', e.target.value)} /></Field>
            <Field label="Bet through (× bonus)" hint="0 = withdrawable at once"><TextInput type="number" min="0" step="0.5" value={form.wagering_multiplier} onChange={(e) => set('wagering_multiplier', e.target.value)} /></Field>
            <Field label="How often">
              <Select value={form.limit} onChange={(e) => set('limit', e.target.value as Limit)}>
                {LIMITS.map((l) => <option key={l.id} value={l.id}>{l.label}</option>)}
              </Select>
            </Field>
            <Field label="Starts" hint="Empty = now"><TextInput type="datetime-local" value={form.starts_at} onChange={(e) => set('starts_at', e.target.value)} /></Field>
            <Field label="Ends" hint="Empty = no end"><TextInput type="datetime-local" value={form.ends_at} onChange={(e) => set('ends_at', e.target.value)} /></Field>
          </div>
          <label className="flex items-center gap-2 text-sm font-medium">
            <Switch checked={form.active} onChange={(v) => set('active', v)} label="Active" /> Active
          </label>
          {preview && <p className="rounded-lg bg-win/10 px-3 py-2 text-sm text-win">{preview}</p>}
          {error && <p className="text-sm font-semibold text-destructive">{error}</p>}
        </div>
      </Drawer>
    </Panel>
  );
}
