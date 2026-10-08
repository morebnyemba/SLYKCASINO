'use client';

import { useEffect, useState } from 'react';
import { BsArrowDown, BsArrowUp, BsCreditCard2Front, BsPencil, BsPlusLg, BsTrash3 } from 'react-icons/bs';
import {
  Badge, Btn, Drawer, EmptyState, Field, Notice, PageHeader, Panel, Select, Switch, TextInput,
  cx, tableClass, tdClass, thClass, trClass,
} from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';
import { LoadingState } from '@slyk/ui/components/spinner';

type FieldType = 'phone' | 'card' | 'crypto' | 'none';

interface Method {
  id: number;
  code: string;
  name: string;
  description: string;
  speed: string;
  logo_text: string;
  color: string;
  field: FieldType;
  min_deposit: string;
  max_deposit: string | null;
  deposit_enabled: boolean;
  show_in_footer: boolean;
  sort_order: number;
  gateway_supported: boolean;
}

interface Listing {
  gateway: 'paynow' | 'stub';
  gateway_methods: string[];
  results: Method[];
}

const FIELD_LABELS: Record<FieldType, string> = {
  phone: 'Mobile number', card: 'Card (Paynow checkout page)', crypto: 'Crypto address', none: 'Nothing',
};

const EMPTY = {
  code: '', name: '', description: '', speed: 'Instant', logo_text: '', color: '#4f46e5', field: 'phone' as FieldType,
  min_deposit: '1.00', max_deposit: '', deposit_enabled: true, show_in_footer: true,
};

/** The logo tile exactly as the player deposit screen draws it. */
function LogoTile({ text, color, size = 40 }: { text: string; color: string; size?: number }) {
  return (
    <span
      style={{ width: size, height: size, background: `linear-gradient(135deg, ${color}, color-mix(in srgb, ${color} 55%, black))` }}
      className="flex shrink-0 items-center justify-center rounded-xl text-[13px] font-extrabold text-white"
    >
      {text}
    </span>
  );
}

function limits(m: Pick<Method, 'min_deposit' | 'max_deposit'>) {
  const min = `$${Number(m.min_deposit).toFixed(2)}`;
  return m.max_deposit ? `${min} – $${Number(m.max_deposit).toFixed(2)}` : `from ${min}`;
}

function MethodDrawer({ method, open, gateway, gatewayMethods, onClose, onSaved }: {
  method: Method | null; open: boolean; gateway: Listing['gateway']; gatewayMethods: string[];
  onClose: () => void; onSaved: (text: string) => void;
}) {
  const { accessToken } = useAuth();
  const [form, setForm] = useState({ ...EMPTY });
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    setError('');
    setForm(method ? {
      code: method.code, name: method.name, description: method.description, speed: method.speed,
      logo_text: method.logo_text, color: method.color, field: method.field, min_deposit: method.min_deposit,
      max_deposit: method.max_deposit ?? '', deposit_enabled: method.deposit_enabled, show_in_footer: method.show_in_footer,
    } : { ...EMPTY });
  }, [method, open]);
  const set = <K extends keyof typeof EMPTY>(k: K, v: (typeof EMPTY)[K]) => setForm((f) => ({ ...f, [k]: v }));

  const unsupported = gateway === 'paynow' && form.code && !gatewayMethods.includes(form.code);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!accessToken) return;
    setBusy(true); setError('');
    const body = { ...form, max_deposit: form.max_deposit === '' ? null : form.max_deposit };
    const res = method
      ? await authedRequest('PATCH', `/admin/payment-methods/${method.id}/`, accessToken, body)
      : await authedRequest('POST', '/admin/payment-methods/', accessToken, body);
    setBusy(false);
    if (res.error) { setError(res.error); return; }
    onSaved(method ? `${form.name} saved.` : `${form.name} added.`);
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title={method ? 'Edit payment method' : 'Add payment method'}
      description="Changes show on the deposit screen and footer straight away."
      footer={<><Btn onClick={onClose}>Cancel</Btn><Btn variant="primary" type="submit" form="method-form" busy={busy}>{method ? 'Save method' : 'Add method'}</Btn></>}
    >
      <form id="method-form" onSubmit={submit} className="space-y-4">
        {/* Live preview of the player's deposit row */}
        <div className="flex items-center gap-3 rounded-2xl border border-border bg-muted/30 px-3.5 py-3">
          <LogoTile text={form.logo_text || form.name.slice(0, 2).toUpperCase() || '?'} color={/^#[0-9a-f]{6}$/i.test(form.color) ? form.color : '#4f46e5'} />
          <span className="min-w-0 flex-1">
            <span className="block truncate text-sm font-bold">{form.name || 'Method name'}</span>
            <span className="block truncate text-[11.5px] text-muted-foreground">
              {[form.description, Number(form.min_deposit) > 0 ? `min $${Number(form.min_deposit)}` : ''].filter(Boolean).join(' · ') || 'Description'}
            </span>
          </span>
          {form.speed && <span className="rounded-md bg-win/15 px-2 py-1 text-[10.5px] font-bold text-win">{form.speed}</span>}
        </div>
        {unsupported && (
          <Notice tone="indigo">
            Paynow can’t process “{form.code}”, so players won’t see it on the deposit screen. It can still appear in the footer.
          </Notice>
        )}
        {error && <Notice tone="red">{error}</Notice>}

        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Name"><TextInput required value={form.name} onChange={(e) => set('name', e.target.value)} placeholder="EcoCash" /></Field>
          <Field label="Code" hint={method ? 'Fixed — it links the method to the payment gateway.' : `Paynow codes: ${gatewayMethods.join(', ')}`}>
            <TextInput
              required disabled={!!method} value={form.code} placeholder="ecocash"
              onChange={(e) => set('code', e.target.value.toLowerCase().replace(/[^a-z0-9-_]/g, ''))}
            />
          </Field>
          <Field label="Description" className="sm:col-span-2"><TextInput value={form.description} onChange={(e) => set('description', e.target.value)} placeholder="Mobile money" /></Field>
          <Field label="Speed label"><TextInput value={form.speed} onChange={(e) => set('speed', e.target.value)} placeholder="Instant" /></Field>
          <Field label="Player enters">
            <Select value={form.field} onChange={(e) => set('field', e.target.value as FieldType)}>
              {(Object.keys(FIELD_LABELS) as FieldType[]).map((f) => <option key={f} value={f}>{FIELD_LABELS[f]}</option>)}
            </Select>
          </Field>
          <Field label="Logo letters" hint="Up to 3 characters.">
            <TextInput maxLength={3} value={form.logo_text} onChange={(e) => set('logo_text', e.target.value)} placeholder="EC" />
          </Field>
          <Field label="Logo colour">
            <div className="flex gap-2">
              <input
                type="color" value={/^#[0-9a-f]{6}$/i.test(form.color) ? form.color : '#4f46e5'}
                onChange={(e) => set('color', e.target.value)}
                className="h-10 w-12 shrink-0 cursor-pointer rounded-xl border border-border bg-transparent p-1"
                aria-label="Pick colour"
              />
              <TextInput value={form.color} onChange={(e) => set('color', e.target.value)} placeholder="#e2231a" />
            </div>
          </Field>
          <Field label="Minimum deposit ($)">
            <TextInput required inputMode="decimal" value={form.min_deposit} onChange={(e) => set('min_deposit', e.target.value.replace(/[^0-9.]/g, ''))} />
          </Field>
          <Field label="Maximum deposit ($)" hint="Leave empty for no maximum.">
            <TextInput inputMode="decimal" value={form.max_deposit} onChange={(e) => set('max_deposit', e.target.value.replace(/[^0-9.]/g, ''))} placeholder="No maximum" />
          </Field>
        </div>

        <div className="space-y-3 rounded-xl border border-border/70 p-4">
          <label className="flex items-center justify-between gap-4">
            <span>
              <span className="block text-sm font-semibold">Offer for deposits</span>
              <span className="block text-xs text-muted-foreground">Show it on the player deposit screen.</span>
            </span>
            <Switch checked={form.deposit_enabled} onChange={(v) => set('deposit_enabled', v)} label="Offer for deposits" />
          </label>
          <label className="flex items-center justify-between gap-4">
            <span>
              <span className="block text-sm font-semibold">Show in footer</span>
              <span className="block text-xs text-muted-foreground">List the name under “Payments” at the bottom of every page.</span>
            </span>
            <Switch checked={form.show_in_footer} onChange={(v) => set('show_in_footer', v)} label="Show in footer" />
          </label>
        </div>
      </form>
    </Drawer>
  );
}

export default function PaymentMethodsPage() {
  const { accessToken } = useAuth();
  const { data, loading, refetch } = useApi<Listing>('/admin/payment-methods/');
  const [editing, setEditing] = useState<Method | null>(null);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const methods = data?.results ?? [];
  const live = data?.gateway === 'paynow';

  async function patch(m: Method, body: Partial<Method>, text: string) {
    if (!accessToken) return;
    setBusyId(m.id);
    const res = await authedRequest('PATCH', `/admin/payment-methods/${m.id}/`, accessToken, body);
    setBusyId(null);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text });
    refetch();
  }

  /** Swap places with the neighbour, then renumber everything 10, 20, 30… */
  async function move(index: number, dir: -1 | 1) {
    if (!accessToken) return;
    const order = [...methods];
    const j = index + dir;
    if (j < 0 || j >= order.length) return;
    [order[index], order[j]] = [order[j], order[index]];
    setBusyId(order[j].id);
    await Promise.all(order.map((m, i) => (m.sort_order === (i + 1) * 10
      ? null : authedRequest('PATCH', `/admin/payment-methods/${m.id}/`, accessToken, { sort_order: (i + 1) * 10 }))));
    setBusyId(null);
    refetch();
  }

  async function remove(m: Method) {
    if (!accessToken || !confirm(`Delete ${m.name}? Past deposits keep their records. To hide it for now, switch it off instead.`)) return;
    const res = await authedRequest('DELETE', `/admin/payment-methods/${m.id}/`, accessToken);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: `${m.name} deleted.` });
    refetch();
  }

  const open = (m: Method | null) => { setEditing(m); setDrawerOpen(true); };

  const status = (m: Method) => !m.deposit_enabled
    ? <Badge tone="slate">Off</Badge>
    : !m.gateway_supported
      ? <Badge tone="gold">Not processed by Paynow</Badge>
      : <Badge tone="green" dot>On the deposit screen</Badge>;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={BsCreditCard2Front}
        eyebrow="Money"
        title="Payment methods"
        description="What players can deposit with, in what order, and the limits for each — plus the payment names in the site footer."
        actions={<Btn variant="primary" icon={BsPlusLg} onClick={() => open(null)}>Add method</Btn>}
      />

      {data && (
        <Notice tone={live ? 'green' : 'indigo'}>
          {live
            ? <>Live gateway: <b>Paynow</b>. It can process {data.gateway_methods.join(', ')} — other methods stay off the deposit screen.</>
            : <>Test processor: deposits credit instantly and no money moves. Set <code>PSP_PROVIDER=paynow</code> on the server to take real payments.</>}
        </Notice>
      )}
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}

      <Panel title="Deposit methods" description="Players see them in this order. Use the arrows to reorder." padded={false}>
        {loading && !data ? (
          <div className="p-10"><LoadingState /></div>
        ) : methods.length === 0 ? (
          <EmptyState icon={BsCreditCard2Front} title="No payment methods" action={<Btn variant="primary" icon={BsPlusLg} onClick={() => open(null)}>Add method</Btn>}>
            Add the ways players can pay in.
          </EmptyState>
        ) : (
          <>
            {/* Desktop table */}
            <div className="hidden overflow-x-auto md:block">
              <table className={tableClass}>
                <thead>
                  <tr>
                    <th className={thClass}>Order</th>
                    <th className={thClass}>Method</th>
                    <th className={thClass}>Limits</th>
                    <th className={thClass}>Status</th>
                    <th className={thClass}>Deposits</th>
                    <th className={thClass}>Footer</th>
                    <th className={thClass} />
                  </tr>
                </thead>
                <tbody>
                  {methods.map((m, i) => (
                    <tr key={m.id} className={cx(trClass, busyId === m.id && 'opacity-60')}>
                      <td className={tdClass}>
                        <div className="flex gap-1">
                          <Btn size="sm" variant="ghost" aria-label="Move up" disabled={i === 0} onClick={() => move(i, -1)}><BsArrowUp /></Btn>
                          <Btn size="sm" variant="ghost" aria-label="Move down" disabled={i === methods.length - 1} onClick={() => move(i, 1)}><BsArrowDown /></Btn>
                        </div>
                      </td>
                      <td className={tdClass}>
                        <div className="flex items-center gap-3">
                          <LogoTile text={m.logo_text || m.name.slice(0, 2).toUpperCase()} color={m.color} size={36} />
                          <span className="min-w-0">
                            <span className="block font-semibold">{m.name}</span>
                            <span className="block text-xs text-muted-foreground">{m.description || '—'} · <code>{m.code}</code></span>
                          </span>
                        </div>
                      </td>
                      <td className={cx(tdClass, 'whitespace-nowrap tabular-nums')}>{limits(m)}</td>
                      <td className={tdClass}>{status(m)}</td>
                      <td className={tdClass}>
                        <Switch checked={m.deposit_enabled} label={`Offer ${m.name} for deposits`}
                          onChange={(v) => patch(m, { deposit_enabled: v }, `${m.name} ${v ? 'is on the deposit screen' : 'is switched off'}.`)} />
                      </td>
                      <td className={tdClass}>
                        <Switch checked={m.show_in_footer} label={`Show ${m.name} in footer`}
                          onChange={(v) => patch(m, { show_in_footer: v }, `${m.name} ${v ? 'shown in' : 'removed from'} the footer.`)} />
                      </td>
                      <td className={cx(tdClass, 'text-right')}>
                        <div className="flex justify-end gap-1">
                          <Btn size="sm" icon={BsPencil} onClick={() => open(m)}>Edit</Btn>
                          <Btn size="sm" variant="ghost" aria-label={`Delete ${m.name}`} onClick={() => remove(m)}><BsTrash3 /></Btn>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>

            {/* Phone cards */}
            <ul className="divide-y divide-border/60 md:hidden">
              {methods.map((m, i) => (
                <li key={m.id} className={cx('space-y-3 p-4', busyId === m.id && 'opacity-60')}>
                  <div className="flex items-center gap-3">
                    <LogoTile text={m.logo_text || m.name.slice(0, 2).toUpperCase()} color={m.color} />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate font-semibold">{m.name}</span>
                      <span className="block text-xs text-muted-foreground">{limits(m)}</span>
                    </span>
                    <Btn size="sm" icon={BsPencil} onClick={() => open(m)}>Edit</Btn>
                  </div>
                  <div>{status(m)}</div>
                  <div className="flex items-center gap-4 text-xs font-semibold text-muted-foreground">
                    <label className="flex items-center gap-2">
                      <Switch checked={m.deposit_enabled} label={`Offer ${m.name} for deposits`}
                        onChange={(v) => patch(m, { deposit_enabled: v }, `${m.name} ${v ? 'is on the deposit screen' : 'is switched off'}.`)} />
                      Deposits
                    </label>
                    <label className="flex items-center gap-2">
                      <Switch checked={m.show_in_footer} label={`Show ${m.name} in footer`}
                        onChange={(v) => patch(m, { show_in_footer: v }, `${m.name} ${v ? 'shown in' : 'removed from'} the footer.`)} />
                      Footer
                    </label>
                    <span className="ml-auto flex gap-1">
                      <Btn size="sm" variant="ghost" aria-label="Move up" disabled={i === 0} onClick={() => move(i, -1)}><BsArrowUp /></Btn>
                      <Btn size="sm" variant="ghost" aria-label="Move down" disabled={i === methods.length - 1} onClick={() => move(i, 1)}><BsArrowDown /></Btn>
                    </span>
                  </div>
                </li>
              ))}
            </ul>
          </>
        )}
      </Panel>

      <MethodDrawer
        method={editing}
        open={drawerOpen}
        gateway={data?.gateway ?? 'stub'}
        gatewayMethods={data?.gateway_methods ?? []}
        onClose={() => setDrawerOpen(false)}
        onSaved={(text) => { setDrawerOpen(false); setNotice({ tone: 'green', text }); refetch(); }}
      />
    </div>
  );
}
