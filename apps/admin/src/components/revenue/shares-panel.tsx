'use client';

import { useEffect, useState } from 'react';
import { BsPeople, BsPieChart } from 'react-icons/bs';
import {
  Badge, Btn, EmptyState, Field, Panel, Select, TextInput, cx, money, tableClass, tdClass, thClass, trClass,
} from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost, authedRequest, useApi } from '@/lib/use-api';

interface Price {
  days: number; months: number; window: number; price_per_percent: string | null; monthly_per_percent: string | null;
  factor: string | null; volatility: string | null; losing_days: number | null; from: string | null; to: string | null; reason: string;
}
interface Change {
  id: number; slot: number; holder: string | null; from_percent: string; to_percent: string; new_holder: string | null;
  reason: string; status: string; status_label: string; requested_by: string; decided_note: string; created_at: string;
  for_sale?: boolean;
}
interface Release { id: number; slot: number; holder: string | null; holder_id: number | null; percent: string; remaining: string; created_at: string }
interface Sale {
  id: number; buyer: string; percent: string; price: string; quoted_price: string | null; status: string; status_label: string;
  payment_method: string; payment_reference: string; note: string; requested_by: string; decided_by: string;
  slot: number | null; created_at: string; expires_at: string | null;
  seller_payouts: { slot: number; holder: string | null; percent: string; amount: string }[]; house_amount: string | null;
  agreement_version: string; agreement_sha256: string; agreement_accepted_at: string | null; agreement_confirmed_by: string;
}
interface Agreement { version: string; title: string; sha256: string; sections: { heading: string; paragraphs: string[] }[] }
interface SharesView {
  can_admin: boolean; is_controller: boolean; controllers: string[]; is_buyer: boolean; own_slot: number | null;
  settings: { partner_pool_percent: string; price_months: number; signer_min_percent: string; seller_percent: string };
  held_percent: string; unsold_percent: string; price: Price; released_percent: string; releases: Release[];
  agreement: Agreement;
  wallets: { slot: number; label: string; holder: string | null; holder_id: number | null; percent: string; protected: boolean }[];
  sales: Sale[]; changes: Change[]; pending_for_me: Change[];
  buyers: { user_id: number; username: string; approved_by: string }[];
  staff: { id: number; username: string }[];
  result?: { applied: boolean; change: Change | null };
}

const pct = (v: string | number) => `${Number(v).toFixed(2).replace(/\.?0+$/, '')}%`;
const SALE_TONE: Record<string, 'gold' | 'green' | 'red' | 'slate'> = { requested: 'gold', confirmed: 'green', rejected: 'red', cancelled: 'slate' };

/**
 * Shares of the partner pool (30% of each day's GGR by default): who holds what,
 * what's unsold, today's price from the last 30 days, selling, buyers' requests,
 * adding members. Admins' changes apply at once (no approvals). Shown to superusers, holders and
 * approved buyers (the API decides who sees what).
 */
export function SharesPanel({ onDone, onFail }: { onDone: (t: string) => void; onFail: (t: string) => void }) {
  const { accessToken } = useAuth();
  const { data, error, refetch } = useApi<SharesView>('/admin/revenue-share/shares/');
  const [view, setView] = useState<SharesView | null>(null);
  useEffect(() => { if (data) setView(data); }, [data]);
  if (error || !view) return null;

  async function act(path: string, body: unknown, ok: string) {
    if (!accessToken) return false;
    const res = await authedPost<SharesView>(`/admin/revenue-share/shares/${path}`, body, accessToken);
    if (res.error || !res.data) { onFail(res.error ?? 'Something went wrong.'); return false; }
    setView(res.data);
    const waiting = res.data.result && !res.data.result.applied;
    onDone(waiting ? `Sent to ${res.data.result!.change?.holder} to approve — nothing changes until they do.` : ok);
    refetch();
    return true;
  }

  const p = view.price;
  return (
    <>
      {view.pending_for_me.length > 0 && <Consent rows={view.pending_for_me} act={act} />}
      <Panel title="Shares" description={`Shareholders split ${pct(view.settings.partner_pool_percent)} of every day’s real-money GGR, each by their own share. Whatever isn’t held is saved in the Savings account until it’s sold.`}>
        <div className="grid gap-3 sm:grid-cols-4">
          <Tile label="Partner pool" value={pct(view.settings.partner_pool_percent)} />
          <Tile label="Held" value={pct(view.held_percent)} />
          <Tile label="Unsold" value={Number(view.released_percent) > 0 ? `${pct(view.unsold_percent)} · ${pct(view.released_percent)} released` : pct(view.unsold_percent)} strong />
          <Tile label="Price of 1%" value={p.price_per_percent ? money(p.price_per_percent) : '—'} strong />
        </div>
        <PriceNote p={p} />
        {(view.can_admin || view.is_controller) && <AddMember view={view} act={act} />}
        {view.controllers.length > 0 && (
          <p className="mt-3 text-xs text-muted-foreground">
            Superusers and share controllers (<b className="text-foreground">{view.controllers.join(', ')}</b>) change shares and add
            members at once, with no approval from anyone. Every change is logged.
          </p>
        )}
        <div className="mt-4 overflow-x-auto">
          <table className={tableClass}>
            <thead><tr>
              <th className={thClass}>Wallet</th><th className={thClass}>Holder</th><th className={thClass}>Share</th>
              {(view.can_admin || view.is_controller || view.own_slot) && <th className={thClass}>Change</th>}
            </tr></thead>
            <tbody>
              {view.wallets.map((w) => (
                <WalletRow key={w.slot} w={w} view={view} act={act} />
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
      {view.can_admin && <SellForm view={view} act={act} />}
      {!view.can_admin && view.is_buyer && <BuyForm view={view} act={act} />}
      <SalesTable view={view} act={act} />
      {view.can_admin && <Buyers view={view} act={act} />}
      {view.releases.length > 0 && <Releases view={view} act={act} />}
      {view.changes.length > 0 && <ChangesLog rows={view.changes} />}
      {view.can_admin && <ShareSettings view={view} act={act} />}
    </>
  );
}

type Act = (path: string, body: unknown, ok: string) => Promise<boolean>;

/** Add a staff login as a revenue-share member: a wallet in the next free slot and a share from the unsold part. */
function AddMember({ view, act }: { view: SharesView; act: Act }) {
  const [open, setOpen] = useState(false);
  const [user, setUser] = useState('');
  const [share, setShare] = useState('0');
  const [label, setLabel] = useState('');
  const [busy, setBusy] = useState(false);
  const holders = new Set(view.wallets.map((w) => w.holder_id).filter(Boolean));
  const candidates = view.staff.filter((u) => !holders.has(u.id));
  async function add() {
    setBusy(true);
    const name = candidates.find((u) => String(u.id) === user)?.username ?? 'The member';
    if (await act('member-add/', { user_id: Number(user), percent: share || '0', label },
      `${name} added with ${pct(share || 0)}.`)) {
      setOpen(false); setUser(''); setShare('0'); setLabel('');
    }
    setBusy(false);
  }
  if (!open) {
    return (
      <div className="mt-4">
        <Btn variant="primary" onClick={() => setOpen(true)}>+ Add member</Btn>
      </div>
    );
  }
  return (
    <div className="mt-4 space-y-3 rounded-xl border border-dashed border-border p-4">
      <p className="text-sm font-bold">Add a member</p>
      <p className="text-xs text-muted-foreground">
        Members need a staff login (they see their own wallet here). Their share comes out of the unsold part: {pct(view.unsold_percent)} is free
        now. Lower another wallet first to make room, or add them with 0% and raise it later. A staff login can open the whole admin console.
      </p>
      <div className="flex flex-wrap items-end gap-3">
        <div className="w-52">
          <Select value={user} onChange={(e) => setUser(e.target.value)} aria-label="Staff login to add">
            <option value="">Choose a staff login…</option>
            {candidates.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
          </Select>
        </div>
        <div className="w-28">
          <TextInput value={share} inputMode="decimal" aria-label="Share (%)" placeholder="Share %"
            onChange={(e) => setShare(e.target.value.replace(/[^0-9.]/g, ''))} />
        </div>
        <div className="w-56">
          <TextInput value={label} maxLength={60} aria-label="Wallet name (optional)" placeholder="Wallet name (optional)"
            onChange={(e) => setLabel(e.target.value)} />
        </div>
        <Btn variant="primary" busy={busy} disabled={!user || Number(share) > Number(view.unsold_percent)} onClick={add}>Add member</Btn>
        <Btn onClick={() => setOpen(false)}>Cancel</Btn>
      </div>
      {Number(share) > Number(view.unsold_percent) && (
        <p className="text-xs text-live">Only {pct(view.unsold_percent)} is unsold.</p>
      )}
      {candidates.length === 0 && <p className="text-xs text-muted-foreground">Every staff login already holds a wallet.</p>}
    </div>
  );
}

function Tile({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <div className="rounded-xl bg-muted/50 p-3">
      <p className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className={cx('mt-0.5 tabular-nums', strong ? 'text-xl font-extrabold' : 'font-semibold')}>{value}</p>
    </div>
  );
}

function PriceNote({ p }: { p: Price }) {
  if (!p.price_per_percent) return <p className="mt-3 text-xs text-muted-foreground">No formula price yet: {p.reason}</p>;
  return (
    <p className="mt-3 text-xs leading-relaxed text-muted-foreground">
      Price from the last {p.days} days ({p.from} to {p.to}): 1% earned about <b className="text-foreground">{money(p.monthly_per_percent!)}</b> a month
      × <b className="text-foreground">{p.months} months</b> × steadiness <b className="text-foreground">{p.factor}</b>
      {' '}(1.000 = every day steady and winning; jumpy or losing days lower it, never below 0.60 — {p.losing_days} losing day{p.losing_days === 1 ? '' : 's'}, volatility {p.volatility}).
    </p>
  );
}

function WalletRow({ w, view, act }: { w: SharesView['wallets'][number]; view: SharesView; act: Act }) {
  const [value, setValue] = useState(w.percent);
  const [busy, setBusy] = useState(false);
  useEffect(() => { setValue(w.percent); }, [w.percent]);
  const own = view.own_slot === w.slot;
  const power = view.can_admin || view.is_controller;
  const editable = power || own;
  const lower = Number(value) < Number(w.percent);
  // A lowered share is sold for the holder (they get the seller's part of the price) unless given back to the house.
  const [forSale, setForSale] = useState(true);
  async function save() {
    setBusy(true);
    await act('set/', { slot: w.slot, percent: value, for_sale: forSale },
      lower && forSale ? `Wallet ${w.slot} is now ${pct(value)}; the ${pct(Number(w.percent) - Number(value))} freed is up for sale for ${w.holder ?? 'the wallet'}.`
        : `Wallet ${w.slot} is now ${pct(value)}.`);
    setBusy(false);
  }
  return (
    <tr className={trClass}>
      <td className={tdClass}>{w.label}<p className="text-xs text-muted-foreground">Wallet {w.slot}</p></td>
      <td className={tdClass}>{w.holder ?? <span className="text-muted-foreground">Nobody yet</span>}</td>
      <td className={cx(tdClass, 'font-semibold tabular-nums')}>{pct(w.percent)}</td>
      {(power || view.own_slot) && (
        <td className={tdClass}>
          {editable && (
            <div className="flex flex-wrap items-center gap-2">
              {/* The kit's inputs are full width: the wrappers set each control's size. */}
              <div className="w-20 shrink-0">
                <TextInput value={value} inputMode="decimal" aria-label={`Share of wallet ${w.slot} (%)`}
                  onChange={(e) => setValue(e.target.value.replace(/[^0-9.]/g, ''))} className="h-8 text-xs" />
              </div>
              <Btn size="sm" busy={busy} disabled={Number(value) === Number(w.percent) || (!power && !lower)} onClick={save}>
                Save
              </Btn>
              {lower && (
                <label className="flex items-center gap-1.5 text-xs text-muted-foreground">
                  <input type="checkbox" checked={forSale} onChange={(e) => setForSale(e.target.checked)} />
                  Sell it for {own ? 'me' : (w.holder ?? 'them')} ({pct(view.settings.seller_percent)} of the price)
                </label>
              )}
            </div>
          )}
        </td>
      )}
    </tr>
  );
}

function Consent({ rows, act }: { rows: Change[]; act: Act }) {
  return (
    <Panel title="Waiting for your approval" description="A change to your share only happens if you approve it.">
      <div className="space-y-2">
        {rows.map((c) => (
          <div key={c.id} className="flex flex-wrap items-center gap-3 rounded-xl border border-secondary/40 bg-secondary/5 p-3 text-sm">
            <p className="min-w-0 flex-1">
              <b>{c.requested_by}</b> asks to {c.new_holder ? <>hand your wallet {c.slot} to <b>{c.new_holder}</b></> : <>change your share from <b>{pct(c.from_percent)}</b> to <b>{pct(c.to_percent)}</b></>}
              {c.reason && <span className="text-muted-foreground"> — “{c.reason}”</span>}
            </p>
            <Btn size="sm" variant="success" onClick={() => act(`changes/${c.id}/`, { approve: true }, 'Approved — your share is updated.')}>Approve</Btn>
            <Btn size="sm" variant="danger" onClick={() => act(`changes/${c.id}/`, { approve: false }, 'Refused — your share stays as it is.')}>Refuse</Btn>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function useQuote(percent: string) {
  const { accessToken } = useAuth();
  const [total, setTotal] = useState<string | null>(null);
  useEffect(() => {
    if (!accessToken || !(Number(percent) > 0)) { setTotal(null); return; }
    const t = setTimeout(async () => {
      const res = await authedRequest<{ total: string | null }>('GET', `/admin/revenue-share/shares/quote/?percent=${encodeURIComponent(percent)}`, accessToken);
      setTotal(res.data?.total ?? null);
    }, 300);
    return () => clearTimeout(t);
  }, [percent, accessToken]);
  return total;
}

/** The purchase agreement and risk disclosure, readable in place, with the box
 *  that must be ticked before a sale or a request can be sent. */
function AgreementBox({ agreement, checked, onChange, label }: {
  agreement: Agreement; checked: boolean; onChange: (v: boolean) => void; label: string;
}) {
  return (
    <div className="mt-3 rounded-lg border border-amber-400/60 bg-amber-400/10 p-3 text-sm">
      <p className="font-semibold text-amber-600 dark:text-amber-300">Risk warning: you may lose the whole price. Payouts depend on daily GGR, can be zero for long periods, and are not guaranteed.</p>
      <details className="mt-2">
        <summary className="cursor-pointer font-medium text-primary">Read the {agreement.title.toLowerCase()} (version {agreement.version})</summary>
        <div className="mt-2 max-h-80 space-y-3 overflow-y-auto rounded-md border border-border bg-background p-3 text-xs leading-relaxed">
          {agreement.sections.map((sec, i) => (
            <section key={sec.heading}>
              <h4 className="mb-1 font-semibold">{i + 1}. {sec.heading}</h4>
              {sec.paragraphs.map((t) => <p key={t} className="mb-1.5">{t}</p>)}
            </section>
          ))}
          <p className="text-[10px] text-muted-foreground">Fingerprint: {agreement.sha256.slice(0, 16)}… — recorded with the sale.</p>
        </div>
      </details>
      <label className="mt-2 flex items-start gap-2">
        <input type="checkbox" className="mt-0.5 h-4 w-4 accent-primary" checked={checked} onChange={(e) => onChange(e.target.checked)} />
        <span>{label}</span>
      </label>
    </div>
  );
}

function SellForm({ view, act }: { view: SharesView; act: Act }) {
  const [buyer, setBuyer] = useState('');
  const [percent, setPercent] = useState('');
  const [price, setPrice] = useState('');
  const [method, setMethod] = useState('EcoCash');
  const [reference, setReference] = useState('');
  const [note, setNote] = useState('');
  const [signed, setSigned] = useState(false);
  const [busy, setBusy] = useState(false);
  const quote = useQuote(percent);
  async function sell() {
    setBusy(true);
    const ok = await act('sale/', { buyer_id: Number(buyer), percent, price: price || null, payment_method: method, payment_reference: reference, note,
      accepted_agreement: signed }, `Sold ${pct(percent)} — it earns from today’s close.`);
    setBusy(false);
    if (ok) { setPercent(''); setPrice(''); setReference(''); setNote(''); setSigned(false); }
  }
  return (
    <Panel title="Sell shares" description={`Record a share that has been paid for (cash, EcoCash or bank — outside the site). Up to ${pct(view.unsold_percent)} is unsold. The buyer needs a staff login; they see only their own wallet.`}>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        <Field label="Buyer">
          <Select value={buyer} onChange={(e) => setBuyer(e.target.value)}>
            <option value="">Choose a staff login…</option>
            {view.staff.map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
          </Select>
        </Field>
        <Field label="Share (%)" hint={quote ? `Formula price: ${money(quote)}` : view.price.reason || 'Enter a share to see the price.'}>
          <TextInput inputMode="decimal" value={percent} onChange={(e) => setPercent(e.target.value.replace(/[^0-9.]/g, ''))} placeholder="2.5" />
        </Field>
        <Field label="Agreed price ($)" hint="Leave empty to use the formula price.">
          <TextInput inputMode="decimal" value={price} onChange={(e) => setPrice(e.target.value.replace(/[^0-9.]/g, ''))} placeholder={quote ?? ''} />
        </Field>
        <Field label="Paid by">
          <Select value={method} onChange={(e) => setMethod(e.target.value)}>
            {['EcoCash', 'Bank transfer', 'Cash', 'InnBucks', 'Other'].map((m) => <option key={m}>{m}</option>)}
          </Select>
        </Field>
        <Field label="Payment reference">
          <TextInput value={reference} onChange={(e) => setReference(e.target.value)} placeholder="Receipt / transaction number" />
        </Field>
        <Field label="Note (optional)"><TextInput value={note} onChange={(e) => setNote(e.target.value)} /></Field>
      </div>
      <AgreementBox agreement={view.agreement} checked={signed} onChange={setSigned}
        label={`The buyer has read and signed the purchase agreement and risk disclosure (version ${view.agreement.version}). Keep the signed copy.`} />
      <div className="mt-3 flex justify-end">
        <Btn variant="primary" busy={busy} disabled={!signed || !buyer || !(Number(percent) > 0) || reference.trim().length < 2 || (!price && !quote)} onClick={sell}>
          Record sale{percent ? ` of ${pct(percent)}` : ''}{(price || quote) ? ` for ${money(price || quote!)}` : ''}
        </Btn>
      </div>
    </Panel>
  );
}

function BuyForm({ view, act }: { view: SharesView; act: Act }) {
  const [percent, setPercent] = useState('');
  const [accepted, setAccepted] = useState(false);
  const [busy, setBusy] = useState(false);
  const quote = useQuote(percent);
  const waiting = view.sales.find((s) => s.status === 'requested');
  if (waiting) {
    return (
      <Panel title="Your purchase">
        <p className="text-sm">
          You asked for <b>{pct(waiting.percent)}</b> for <b>{money(waiting.price)}</b>. Pay the business (EcoCash, bank or cash) and keep the
          reference — it counts once an admin confirms the payment. This price holds until {waiting.expires_at ? new Date(waiting.expires_at).toLocaleDateString() : '7 days'}.
        </p>
        <div className="mt-3"><Btn size="sm" variant="danger" onClick={() => act(`sales/${waiting.id}/`, { action: 'reject' }, 'Request cancelled.')}>Cancel request</Btn></div>
      </Panel>
    );
  }
  return (
    <Panel title="Buy shares" description={`Up to ${pct(view.unsold_percent)} is unsold. You pay outside the site; your share counts once an admin confirms the payment.`}>
      <div className="flex flex-wrap items-end gap-3">
        <Field label="Share (%)" className="w-40">
          <TextInput inputMode="decimal" value={percent} onChange={(e) => setPercent(e.target.value.replace(/[^0-9.]/g, ''))} placeholder="1" />
        </Field>
        <p className="pb-2 text-sm text-muted-foreground">{quote ? <>Price: <b className="text-foreground">{money(quote)}</b></> : view.price.reason}</p>
        <Btn variant="primary" busy={busy} disabled={!quote || !accepted} onClick={async () => {
          setBusy(true);
          await act('buy/', { percent, accepted_agreement: accepted }, 'Request sent — pay the business, then an admin confirms it.');
          setBusy(false);
        }}>Ask to buy</Btn>
      </div>
      <AgreementBox agreement={view.agreement} checked={accepted} onChange={setAccepted}
        label={`I have read and accept the purchase agreement and risk disclosure (version ${view.agreement.version}). I understand I may lose the whole price and that no return is promised.`} />
    </Panel>
  );
}

function SalesTable({ view, act }: { view: SharesView; act: Act }) {
  if (view.sales.length === 0 && !view.can_admin) return null;
  return (
    <Panel title={view.can_admin ? 'Share sales' : 'My purchases'} padded={false}>
      {view.sales.length === 0 ? <EmptyState icon={BsPieChart} title="No sales yet" /> : (
        <div className="overflow-x-auto">
          <table className={tableClass}>
            <thead><tr>
              <th className={thClass}>Buyer</th><th className={thClass}>Share</th><th className={thClass}>Price</th>
              <th className={thClass}>Status</th><th className={thClass}>When</th>{view.can_admin && <th className={thClass} />}
            </tr></thead>
            <tbody>
              {view.sales.map((s) => <SaleRow key={s.id} s={s} admin={view.can_admin} act={act} />)}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

function SaleRow({ s, admin, act }: { s: Sale; admin: boolean; act: Act }) {
  const [reference, setReference] = useState('');
  return (
    <tr className={trClass}>
      <td className={tdClass}>{s.buyer}{s.slot && <p className="text-xs text-muted-foreground">Wallet {s.slot}</p>}</td>
      <td className={cx(tdClass, 'tabular-nums')}>{pct(s.percent)}</td>
      <td className={cx(tdClass, 'tabular-nums')}>
        {money(s.price)}
        {s.quoted_price && s.quoted_price !== s.price && <p className="text-xs text-muted-foreground">Formula {money(s.quoted_price)}</p>}
        {s.status === 'confirmed' && (s.seller_payouts.length > 0 || s.house_amount) && (
          <p className="text-xs text-muted-foreground">
            {s.seller_payouts.map((p) => `${p.holder ?? `Wallet ${p.slot}`} ${money(p.amount)}`).join(' · ')}
            {s.seller_payouts.length > 0 ? ' · ' : ''}House {money(s.house_amount ?? '0')}
          </p>
        )}
      </td>
      <td className={tdClass}>
        <Badge tone={SALE_TONE[s.status] ?? 'slate'} dot>{s.status_label}</Badge>
        {(s.payment_method || s.payment_reference) && <p className="mt-1 text-xs text-muted-foreground">{[s.payment_method, s.payment_reference].filter(Boolean).join(' · ')}</p>}
        {s.agreement_version && <p className="mt-0.5 text-[11px] text-muted-foreground" title={`Fingerprint ${s.agreement_sha256}`}>Agreement v{s.agreement_version} · confirmed by {s.agreement_confirmed_by}</p>}
      </td>
      <td className={cx(tdClass, 'whitespace-nowrap text-xs text-muted-foreground')}>{new Date(s.created_at).toLocaleDateString()}</td>
      {admin && (
        <td className={tdClass}>
          {s.status === 'requested' && (
            <div className="flex flex-wrap items-center gap-2">
              <div className="w-32 shrink-0">
                <TextInput value={reference} onChange={(e) => setReference(e.target.value)} placeholder="Payment ref" className="h-8 text-xs" />
              </div>
              <Btn size="sm" variant="success" disabled={reference.trim().length < 2}
                onClick={() => act(`sales/${s.id}/`, { action: 'confirm', payment_reference: reference }, `Payment confirmed — ${s.buyer} now holds the share.`)}>
                Confirm paid
              </Btn>
              <Btn size="sm" variant="danger" onClick={() => act(`sales/${s.id}/`, { action: 'reject' }, 'Request rejected.')}>Reject</Btn>
            </div>
          )}
        </td>
      )}
    </tr>
  );
}

function Buyers({ view, act }: { view: SharesView; act: Act }) {
  const [user, setUser] = useState('');
  const approved = new Set(view.buyers.map((b) => b.user_id));
  return (
    <Panel title="Approved buyers" description="Staff logins that may ask to buy shares themselves. Their purchase counts once you confirm the payment.">
      <div className="flex flex-wrap items-center gap-2">
        {view.buyers.length === 0 && <span className="text-sm text-muted-foreground">Nobody yet.</span>}
        {view.buyers.map((b) => (
          <span key={b.user_id} className="inline-flex items-center gap-2 rounded-full border border-border px-3 py-1 text-sm">
            <BsPeople size={12} /> {b.username}
            <button className="text-xs text-live hover:underline" onClick={() => act('buyer-remove/', { user_id: b.user_id }, `${b.username} can no longer ask to buy.`)}>Remove</button>
          </span>
        ))}
      </div>
      <div className="mt-3 flex flex-wrap items-end gap-2">
        <Field label="Add a buyer" className="w-56">
          <Select value={user} onChange={(e) => setUser(e.target.value)}>
            <option value="">Choose a staff login…</option>
            {view.staff.filter((u) => !approved.has(u.id)).map((u) => <option key={u.id} value={u.id}>{u.username}</option>)}
          </Select>
        </Field>
        <Btn disabled={!user} onClick={async () => { if (await act('buyer-add/', { user_id: Number(user) }, 'Buyer approved.')) setUser(''); }}>Approve</Btn>
      </div>
    </Panel>
  );
}

function ChangesLog({ rows }: { rows: Change[] }) {
  return (
    <Panel title="Share changes" padded={false}>
      <div className="overflow-x-auto">
        <table className={tableClass}>
          <thead><tr>
            <th className={thClass}>Wallet</th><th className={thClass}>Change</th><th className={thClass}>Asked by</th><th className={thClass}>Status</th>
          </tr></thead>
          <tbody>
            {rows.map((c) => (
              <tr key={c.id} className={trClass}>
                <td className={tdClass}>Wallet {c.slot}<p className="text-xs text-muted-foreground">{c.holder ?? 'No holder'}</p></td>
                <td className={cx(tdClass, 'text-sm')}>
                  {c.new_holder ? `Hand to ${c.new_holder}` : `${pct(c.from_percent)} → ${pct(c.to_percent)}`}
                  {c.reason && <p className="text-xs text-muted-foreground">{c.reason}</p>}
                </td>
                <td className={cx(tdClass, 'text-xs')}>{c.requested_by}<p className="text-muted-foreground">{new Date(c.created_at).toLocaleDateString()}</p></td>
                <td className={tdClass}>
                  <Badge tone={c.status === 'applied' ? 'green' : c.status === 'pending' ? 'gold' : c.status === 'rejected' ? 'red' : 'slate'} dot>{c.status_label}</Badge>
                  {c.decided_note && <p className="mt-1 text-xs text-muted-foreground">{c.decided_note}</p>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}

function ShareSettings({ view, act }: { view: SharesView; act: Act }) {
  const [pool, setPool] = useState(view.settings.partner_pool_percent);
  const [months, setMonths] = useState(String(view.settings.price_months));
  const [signers, setSigners] = useState(view.settings.signer_min_percent);
  const [seller, setSeller] = useState(view.settings.seller_percent);
  const [busy, setBusy] = useState(false);
  return (
    <Panel title="Share settings">
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        <Field label="Partner pool (%)" hint="The part of each day’s GGR that shareholders split. Can’t go below what’s held.">
          <TextInput inputMode="decimal" value={pool} onChange={(e) => setPool(e.target.value.replace(/[^0-9.]/g, ''))} />
        </Field>
        <Field label="Price = months of earnings" hint="A share costs this many months of what it earned over the last 30 days.">
          <TextInput inputMode="numeric" value={months} onChange={(e) => setMonths(e.target.value.replace(/[^0-9]/g, ''))} />
        </Field>
        <Field label="Co-sign audits from (%)" hint="Holders of at least this share co-sign weekly audits; smaller holders can’t lock the admin.">
          <TextInput inputMode="decimal" value={signers} onChange={(e) => setSigners(e.target.value.replace(/[^0-9.]/g, ''))} />
        </Field>
        <Field label="Seller gets (%)" hint="Of the price when share someone released is sold; the house keeps the rest.">
          <TextInput inputMode="decimal" value={seller} onChange={(e) => setSeller(e.target.value.replace(/[^0-9.]/g, ''))} />
        </Field>
      </div>
      <div className="mt-3 flex justify-end">
        <Btn variant="primary" busy={busy} onClick={async () => {
          setBusy(true);
          await act('settings/', { partner_pool_percent: pool, price_months: months, signer_min_percent: signers, seller_percent: seller }, 'Share settings saved.');
          setBusy(false);
        }}>Save</Btn>
      </div>
    </Panel>
  );
}

function Releases({ view, act }: { view: SharesView; act: Act }) {
  const { user } = useAuth();
  return (
    <Panel title="Up for sale for holders" description={`Share holders gave up to be sold for them. Sales use the oldest first; the holder gets ${pct(view.settings.seller_percent)} of its part of the price in their share wallet. They can take back what hasn’t sold.`} padded={false}>
      <div className="overflow-x-auto">
        <table className={tableClass}>
          <thead><tr>
            <th className={thClass}>Released by</th><th className={thClass}>Released</th><th className={thClass}>Still for sale</th>
            <th className={thClass}>Since</th><th className={thClass} />
          </tr></thead>
          <tbody>
            {view.releases.map((r) => (
              <tr key={r.id} className={trClass}>
                <td className={tdClass}>{r.holder ?? 'No holder'}<p className="text-xs text-muted-foreground">Wallet {r.slot}</p></td>
                <td className={cx(tdClass, 'tabular-nums')}>{pct(r.percent)}</td>
                <td className={cx(tdClass, 'font-semibold tabular-nums')}>{pct(r.remaining)}</td>
                <td className={cx(tdClass, 'whitespace-nowrap text-xs text-muted-foreground')}>{new Date(r.created_at).toLocaleDateString()}</td>
                <td className={tdClass}>
                  {user?.username === r.holder && (
                    <Btn size="sm" onClick={() => act('reclaim/', { release_id: r.id }, `Took back ${pct(r.remaining)} — it’s yours again.`)}>Take back</Btn>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
