'use client';

import { useEffect, useState } from 'react';
import { FaBuildingColumns, FaCheck, FaMobileScreen, FaWallet, FaXmark } from 'react-icons/fa6';
import { Spinner } from '@slyk/ui/components/spinner';
import { useAuth } from '@/lib/auth-context';
import { authedPost } from '@/lib/use-api';

export interface PayoutOptions { methods: { id: string; label: string }[]; min_payout: string; kyc_verified: boolean }

const money = (v: string | number) => `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
const ICON: Record<string, React.ReactNode> = {
  wallet: <FaWallet />, ecocash: <FaMobileScreen />, onemoney: <FaMobileScreen />, innbucks: <FaMobileScreen />, bank: <FaBuildingColumns />,
};
const HINT: Record<string, string> = {
  wallet: 'Instant — bet with it or withdraw it like any balance',
  ecocash: 'Sent to your EcoCash number', onemoney: 'Sent to your OneMoney number', innbucks: 'Sent to your InnBucks number',
  bank: 'Bank transfer to your account',
};

/** Withdraw affiliate earnings: pick where, enter details, confirm. */
export function PayoutDialog({ open, onClose, available, options, onDone }: {
  open: boolean; onClose: () => void; available: string; options: PayoutOptions; onDone: () => void;
}) {
  const { accessToken } = useAuth();
  const [method, setMethod] = useState('wallet');
  const [amount, setAmount] = useState(available);
  const [name, setName] = useState('');
  const [number, setNumber] = useState('');
  const [bank, setBank] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [done, setDone] = useState<string | null>(null);

  // Reset only when the dialog opens — not when the balance refreshes after a
  // successful payout (that would wipe the confirmation).
  useEffect(() => {
    if (!open) return;
    setAmount(available); setError(''); setDone(null); setMethod('wallet');
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, onClose]);
  if (!open) return null;

  const external = method !== 'wallet';
  const mobile = ['ecocash', 'onemoney', 'innbucks'].includes(method);
  const blockedByKyc = external && !options.kyc_verified;
  const tooSmall = external && Number(amount) < Number(options.min_payout);

  async function submit() {
    if (!accessToken) return;
    setBusy(true); setError('');
    const res = await authedPost('/affiliates/me/payouts/', {
      amount, method, account_name: name, account_number: number, bank_name: bank,
    }, accessToken);
    setBusy(false);
    if (res.error) { setError(res.error); return; }
    const label = options.methods.find((m) => m.id === method)?.label ?? method;
    setDone(external ? `Request for ${money(amount)} to ${label} sent — we’ll notify you when it’s paid.` : `${money(amount)} is now in your betting wallet.`);
    onDone();
  }

  const input = 'w-full rounded-lg border border-border bg-input px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring';
  return (
    <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 p-0 backdrop-blur-sm sm:items-center sm:p-4" onClick={onClose}>
      <div role="dialog" aria-modal="true" aria-label="Request a payout" onClick={(e) => e.stopPropagation()}
        className="max-h-[92dvh] w-full max-w-md overflow-y-auto rounded-t-2xl border border-border bg-card p-5 shadow-2xl sm:rounded-2xl">
        <div className="mb-4 flex items-start justify-between gap-3">
          <div>
            <h2 className="text-lg font-extrabold">Request a payout</h2>
            <p className="text-sm text-muted-foreground">Available: <b className="text-foreground">{money(available)}</b></p>
          </div>
          <button onClick={onClose} aria-label="Close" className="rounded-lg p-2 text-muted-foreground hover:bg-muted"><FaXmark /></button>
        </div>

        {done ? (
          <div className="space-y-4 py-4 text-center">
            <span className="mx-auto flex h-12 w-12 items-center justify-center rounded-full bg-win/15 text-win"><FaCheck size={20} /></span>
            <p className="font-semibold">{done}</p>
            <button onClick={onClose} className="w-full rounded-lg bg-secondary py-2.5 text-sm font-bold text-white">Done</button>
          </div>
        ) : (
          <div className="space-y-4">
            <fieldset className="space-y-2">
              <legend className="mb-1 text-xs font-bold uppercase tracking-wide text-muted-foreground">Pay me to</legend>
              {options.methods.map((m) => (
                <label key={m.id} className={`flex cursor-pointer items-center gap-3 rounded-xl border p-3 transition-colors ${method === m.id ? 'border-secondary bg-secondary/10' : 'border-border hover:bg-muted/50'}`}>
                  <input type="radio" name="method" value={m.id} checked={method === m.id} onChange={() => { setMethod(m.id); setError(''); }} className="sr-only" />
                  <span className={`flex h-9 w-9 items-center justify-center rounded-lg ${method === m.id ? 'bg-secondary text-white' : 'bg-muted text-muted-foreground'}`}>{ICON[m.id]}</span>
                  <span className="min-w-0 flex-1">
                    <span className="block text-sm font-bold">{m.label}</span>
                    <span className="block text-xs text-muted-foreground">{HINT[m.id]}</span>
                  </span>
                  {method === m.id && <FaCheck className="text-secondary" />}
                </label>
              ))}
            </fieldset>

            <label className="block space-y-1 text-sm">
              <span className="font-semibold">Amount</span>
              <div className="flex gap-2">
                <input inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value.replace(/[^0-9.]/g, ''))} className={input} />
                <button type="button" onClick={() => setAmount(available)} className="rounded-lg border border-border px-3 text-xs font-bold hover:bg-muted">Max</button>
              </div>
              {external && <span className="text-xs text-muted-foreground">Minimum {money(options.min_payout)} to {options.methods.find((m) => m.id === method)?.label}.</span>}
            </label>

            {mobile && (
              <>
                <label className="block space-y-1 text-sm"><span className="font-semibold">Mobile number</span>
                  <input inputMode="tel" value={number} onChange={(e) => setNumber(e.target.value)} placeholder="0771 234 567" className={input} /></label>
                <label className="block space-y-1 text-sm"><span className="font-semibold">Name on the account</span>
                  <input value={name} onChange={(e) => setName(e.target.value)} placeholder="As registered with the network" className={input} /></label>
              </>
            )}
            {method === 'bank' && (
              <>
                <label className="block space-y-1 text-sm"><span className="font-semibold">Bank</span>
                  <input value={bank} onChange={(e) => setBank(e.target.value)} placeholder="e.g. CBZ, Stanbic, FBC" className={input} /></label>
                <label className="block space-y-1 text-sm"><span className="font-semibold">Account name</span>
                  <input value={name} onChange={(e) => setName(e.target.value)} className={input} /></label>
                <label className="block space-y-1 text-sm"><span className="font-semibold">Account number</span>
                  <input inputMode="numeric" value={number} onChange={(e) => setNumber(e.target.value)} className={input} /></label>
              </>
            )}
            {blockedByKyc && (
              <p className="rounded-lg bg-gold/10 px-3 py-2 text-xs font-semibold text-gold">
                Verify your identity first — <a href="/account/verification" className="underline">upload your ID</a>. You can still move earnings to your betting wallet now.
              </p>
            )}
            {error && <p className="text-sm font-semibold text-destructive">{error}</p>}
            <button onClick={submit} disabled={busy || blockedByKyc || tooSmall || !(Number(amount) > 0) || Number(amount) > Number(available)}
              className="w-full rounded-lg bg-win py-2.5 text-sm font-extrabold text-win-foreground disabled:opacity-50">
              {busy ? <span className="inline-flex items-center gap-2"><Spinner size={14} />Requesting…</span>
                : external ? `Request ${money(amount || 0)}` : `Move ${money(amount || 0)} to my wallet`}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
