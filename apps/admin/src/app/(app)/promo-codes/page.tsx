'use client';

import { useState } from 'react';
import { BsTicket } from 'react-icons/bs';
import {
  Badge, Btn, Drawer, EmptyState, Field, Notice, PageHeader, Select, Switch, TextInput, cx, money,
  tableClass, tdClass, thClass, trClass,
} from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost, authedRequest, useApi } from '@/lib/use-api';

interface PromoCode {
  id: number; code: string; name: string; description: string; active: boolean; kind: 'percent' | 'fixed';
  value: string; max_bonus: string; min_deposit: string; starts_at: string | null; ends_at: string | null;
  max_uses: number; per_player_limit: number; created_by: string; created_at: string; uses: number; total_given: string;
}

type Draft = Omit<PromoCode, 'id' | 'created_by' | 'created_at' | 'uses' | 'total_given' | 'max_uses' | 'per_player_limit'> & {
  max_uses: string; per_player_limit: string;
};

const EMPTY: Draft = {
  code: '', name: '', description: '', active: true, kind: 'percent', value: '100', max_bonus: '0', min_deposit: '1',
  starts_at: null, ends_at: null, max_uses: '0', per_player_limit: '1',
};

const toInput = (iso: string | null) => (iso ? new Date(iso).toISOString().slice(0, 16) : '');
const fromInput = (v: string) => (v ? new Date(v).toISOString() : null);

function offer(p: { kind: string; value: string; max_bonus: string }) {
  return p.kind === 'fixed' ? money(p.value)
    : `${Number(p.value)}% of the deposit${Number(p.max_bonus) > 0 ? ` (up to ${money(p.max_bonus)})` : ''}`;
}

function state(p: PromoCode): { label: string; tone: 'green' | 'slate' | 'gold' | 'red' } {
  const now = Date.now();
  if (!p.active) return { label: 'Deactivated', tone: 'slate' };
  if (p.ends_at && Date.parse(p.ends_at) <= now) return { label: 'Expired', tone: 'slate' };
  if (p.starts_at && Date.parse(p.starts_at) > now) return { label: 'Scheduled', tone: 'gold' };
  if (p.max_uses && p.uses >= p.max_uses) return { label: 'Used up', tone: 'red' };
  return { label: 'Live', tone: 'green' };
}

/** Promo codes players enter when depositing. Their bonus goes to the Bonus wallet. */
export default function PromoCodesPage() {
  const { accessToken } = useAuth();
  const { data, loading, refetch } = useApi<PromoCode[]>('/admin/promo-codes/');
  const [editing, setEditing] = useState<{ id: number | null; draft: Draft } | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  const rows = data ?? [];

  async function save() {
    if (!accessToken || !editing) return;
    setBusy(true);
    const body = { ...editing.draft, max_uses: Number(editing.draft.max_uses) || 0, per_player_limit: Number(editing.draft.per_player_limit) || 0 };
    const res = editing.id
      ? await authedRequest('PATCH', `/admin/promo-codes/${editing.id}/`, accessToken, body)
      : await authedPost('/admin/promo-codes/', body, accessToken);
    setBusy(false);
    if (res.error) { setNotice({ tone: 'red', text: res.error }); return; }
    setNotice({ tone: 'green', text: editing.id ? 'Promo code saved.' : `Promo code ${body.code.toUpperCase()} created.` });
    setEditing(null);
    refetch();
  }

  async function toggle(p: PromoCode) {
    if (!accessToken) return;
    const res = await authedRequest('PATCH', `/admin/promo-codes/${p.id}/`, accessToken, { active: !p.active });
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: `${p.code} ${p.active ? 'deactivated' : 'reactivated'}.` });
    refetch();
  }

  const d = editing?.draft;
  const set = (patch: Partial<Draft>) => setEditing((e) => e && { ...e, draft: { ...e.draft, ...patch } });

  return (
    <div className="space-y-5">
      <PageHeader icon={BsTicket} eyebrow="Marketing" title="Promo codes"
        description="Codes players enter when depositing. The bonus goes into their Bonus wallet (sportsbook only, staked in full on a 10+ selection multiple) and replaces the automatic deposit bonus for that deposit. The fraud engine refuses a code on accounts sharing a payment number."
        actions={<Btn variant="primary" onClick={() => setEditing({ id: null, draft: EMPTY })}>New promo code</Btn>} />
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}

      <div className="overflow-hidden rounded-2xl border border-border/70 bg-card">
        {loading && !data ? <div className="h-40 animate-pulse bg-muted/40" /> : rows.length === 0 ? (
          <EmptyState icon={BsTicket} title="No promo codes yet">Create one and share it with players.</EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className={tableClass}>
              <thead><tr>
                <th className={thClass}>Code</th><th className={thClass}>Gives</th><th className={thClass}>Rules</th>
                <th className={thClass}>Used</th><th className={thClass}>State</th><th className={thClass} />
              </tr></thead>
              <tbody>
                {rows.map((p) => {
                  const st = state(p);
                  return (
                    <tr key={p.id} className={trClass}>
                      <td className={tdClass}><p className="font-mono font-bold">{p.code}</p><p className="text-xs text-muted-foreground">{p.name}</p></td>
                      <td className={tdClass}>{offer(p)}</td>
                      <td className={cx(tdClass, 'text-xs text-muted-foreground')}>
                        Min deposit {money(p.min_deposit)} · {p.per_player_limit ? `${p.per_player_limit} per player` : 'unlimited per player'}
                        {p.max_uses ? ` · ${p.max_uses} total` : ''}
                        {p.ends_at && <> · ends {new Date(p.ends_at).toLocaleDateString()}</>}
                      </td>
                      <td className={cx(tdClass, 'tabular-nums')}>{p.uses} · {money(p.total_given)}</td>
                      <td className={tdClass}><Badge tone={st.tone} dot>{st.label}</Badge></td>
                      <td className={cx(tdClass, 'text-right')}>
                        <div className="flex justify-end gap-2">
                          <Btn size="sm" onClick={() => setEditing({ id: p.id, draft: { ...p, max_uses: String(p.max_uses), per_player_limit: String(p.per_player_limit) } })}>Edit</Btn>
                          <Btn size="sm" variant={p.active ? 'danger' : 'success'} onClick={() => toggle(p)}>{p.active ? 'Deactivate' : 'Reactivate'}</Btn>
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <Drawer open={!!editing} onClose={() => setEditing(null)} title={editing?.id ? `Edit ${d?.code}` : 'New promo code'}
        description="Players type the code (any case) in the deposit form."
        footer={<><Btn onClick={() => setEditing(null)}>Cancel</Btn><Btn variant="primary" busy={busy} onClick={save}
          disabled={!d?.code || !d?.name || !Number(d?.value)}>Save</Btn></>}>
        {d && (
          <div className="space-y-4 text-sm">
            <Field label="Code" hint="3–40 letters, numbers, - or _."><TextInput value={d.code} onChange={(e) => set({ code: e.target.value.toUpperCase() })} placeholder="WELCOME50" /></Field>
            <Field label="Name" hint="Shown to the player."><TextInput value={d.name} onChange={(e) => set({ name: e.target.value })} placeholder="Welcome 50%" /></Field>
            <Field label="Description (optional)"><TextInput value={d.description} onChange={(e) => set({ description: e.target.value })} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Bonus type">
                <Select value={d.kind} onChange={(e) => set({ kind: e.target.value as Draft['kind'] })}>
                  <option value="percent">% of the deposit</option><option value="fixed">Fixed amount</option>
                </Select>
              </Field>
              <Field label={d.kind === 'percent' ? 'Percent' : 'Amount ($)'}>
                <TextInput inputMode="decimal" value={d.value} onChange={(e) => set({ value: e.target.value.replace(/[^0-9.]/g, '') })} />
              </Field>
              {d.kind === 'percent' && (
                <Field label="Most per deposit ($)" hint="0 = no cap.">
                  <TextInput inputMode="decimal" value={d.max_bonus} onChange={(e) => set({ max_bonus: e.target.value.replace(/[^0-9.]/g, '') })} />
                </Field>
              )}
              <Field label="Minimum deposit ($)">
                <TextInput inputMode="decimal" value={d.min_deposit} onChange={(e) => set({ min_deposit: e.target.value.replace(/[^0-9.]/g, '') })} />
              </Field>
              <Field label="Uses per player" hint="0 = unlimited.">
                <TextInput inputMode="numeric" value={d.per_player_limit} onChange={(e) => set({ per_player_limit: e.target.value.replace(/\D/g, '') })} />
              </Field>
              <Field label="Total uses" hint="0 = unlimited.">
                <TextInput inputMode="numeric" value={d.max_uses} onChange={(e) => set({ max_uses: e.target.value.replace(/\D/g, '') })} />
              </Field>
              <Field label="Starts (optional)"><TextInput type="datetime-local" value={toInput(d.starts_at)} onChange={(e) => set({ starts_at: fromInput(e.target.value) })} /></Field>
              <Field label="Ends (optional)"><TextInput type="datetime-local" value={toInput(d.ends_at)} onChange={(e) => set({ ends_at: fromInput(e.target.value) })} /></Field>
            </div>
            <Switch checked={d.active} onChange={(v) => set({ active: v })} label="Active" />
          </div>
        )}
      </Drawer>
    </div>
  );
}
