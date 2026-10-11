'use client';

import { useState } from 'react';
import { FaArrowDown } from 'react-icons/fa';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';

interface Withdrawal {
  id: number; amount: string; method: string; method_label: string; account_number: string;
  status: 'requested' | 'paid' | 'rejected' | 'cancelled'; status_label: string; reference: string; note: string;
  created_at: string;
}
interface Mine {
  results: Withdrawal[];
  limits: { min: string; max: string; daily_max: string; left_today: string | null };
  methods: { id: string; label: string }[];
}

const TONE: Record<Withdrawal['status'], 'default' | 'secondary' | 'destructive'> = {
  requested: 'secondary', paid: 'default', rejected: 'destructive', cancelled: 'secondary',
};
const input = 'w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-secondary';

/** Ask to be paid out, and follow each request until it's sent. Payouts are
 *  sent by the BetBlits team, so a request waits until they mark it paid. */
export function WithdrawPanel({ withdrawable, onChanged }: { withdrawable?: string; onChanged: () => void }) {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<Mine>('/wallet/withdrawals/');
  const [amount, setAmount] = useState('');
  const [method, setMethod] = useState('ecocash');
  const [number, setNumber] = useState('');
  const [name, setName] = useState('');
  const [bank, setBank] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const isBank = method === 'bank';

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!accessToken) return;
    setBusy(true); setMsg(null);
    const { error } = await authedPost('/wallet/withdraw/', {
      amount, method, account_number: number, account_name: name, ...(isBank ? { bank_name: bank } : {}),
    }, accessToken);
    setBusy(false);
    if (error) { setMsg({ ok: false, text: error }); return; }
    setMsg({ ok: true, text: `Request sent — $${Number(amount).toFixed(2)} is on hold for you and will be paid to your ${data?.methods.find((m) => m.id === method)?.label ?? method} shortly.` });
    setAmount('');
    refetch(); onChanged();
  }

  async function cancel(id: number) {
    if (!accessToken || !confirm('Cancel this withdrawal? The money goes back to your balance.')) return;
    const { error } = await authedPost(`/wallet/withdrawals/${id}/cancel/`, {}, accessToken);
    setMsg(error ? { ok: false, text: error } : { ok: true, text: 'Cancelled — the money is back in your balance.' });
    refetch(); onChanged();
  }

  const limits = data?.limits;
  return (
    <div className="space-y-3">
      <p className="text-sm font-medium">Withdraw</p>
      <form onSubmit={submit} className="grid gap-2 sm:grid-cols-2">
        <input type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Amount" aria-label="Amount" className={input} required />
        <select value={method} onChange={(e) => setMethod(e.target.value)} aria-label="Send to" className={input}>
          {(data?.methods ?? [{ id: 'ecocash', label: 'EcoCash' }]).map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
        </select>
        <input value={number} onChange={(e) => setNumber(e.target.value)} placeholder={isBank ? 'Account number' : 'Mobile number, e.g. 0771 234 567'}
          aria-label={isBank ? 'Account number' : 'Mobile number'} inputMode={isBank ? 'text' : 'tel'} className={input} required />
        <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name on the account" aria-label="Account name" className={input} required={isBank} />
        {isBank && <input value={bank} onChange={(e) => setBank(e.target.value)} placeholder="Bank, e.g. CBZ" aria-label="Bank" className={`${input} sm:col-span-2`} required />}
        <button type="submit" disabled={busy || !amount || !number}
          className="flex items-center justify-center gap-1.5 rounded-md bg-secondary px-4 py-2 text-sm font-bold text-secondary-foreground disabled:opacity-50 sm:col-span-2">
          <FaArrowDown size={11} /> {busy ? 'Sending…' : 'Request withdrawal'}
        </button>
      </form>
      <p className="text-xs text-muted-foreground">
        {withdrawable && <>You can withdraw up to <b>${withdrawable}</b>. </>}
        {limits && <>Per request ${limits.min}–${limits.max}{limits.left_today ? `; $${limits.left_today} left today` : ''}. </>}
        The amount is held as soon as you ask and our team sends it — usually within a few hours.
      </p>
      {msg && <p className={`text-sm ${msg.ok ? 'text-win' : 'text-down'}`}>{msg.text}</p>}

      {(data?.results ?? []).length > 0 && (
        <ul className="divide-y divide-border rounded-xl border border-border">
          {data!.results.map((w) => (
            <li key={w.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
              <span className="font-semibold tabular-nums">${w.amount}</span>
              <span className="text-muted-foreground">{w.method_label} {w.account_number}</span>
              <Badge variant={TONE[w.status]}>{w.status_label}</Badge>
              <span className="ml-auto text-xs text-muted-foreground">{new Date(w.created_at).toLocaleString()}</span>
              {w.status === 'requested' && (
                <button onClick={() => cancel(w.id)} className="text-xs font-semibold text-down hover:underline">Cancel</button>
              )}
              {w.status === 'paid' && w.reference && <p className="w-full text-xs text-muted-foreground">Reference: {w.reference}</p>}
              {w.status === 'rejected' && w.note && <p className="w-full text-xs text-down">Reason: {w.note}</p>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
