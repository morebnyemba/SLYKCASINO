'use client';

import { useState } from 'react';
import { FaArrowDown } from 'react-icons/fa';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';
import { useWallets } from '@/lib/wallets';

type Source = 'winnings' | 'deposit';

interface Withdrawal {
  id: number; amount: string; fee?: string; payout_amount?: string; wallet?: Source; wallet_label?: string;
  method: string; method_label: string; account_number: string;
  status: 'requested' | 'paid' | 'rejected' | 'cancelled'; status_label: string; reference: string; note: string;
  created_at: string; legacy?: boolean;
}
interface Mine {
  results: Withdrawal[];
  limits: { min: string; max: string; daily_max: string; left_today: string | null; turnover_left?: string;
    fee_percent?: string; deposit_fee_percent?: string };
  methods: { id: string; label: string }[];
}
interface Quote { wallet: Source; amount: string; fee_percent: string; fee: string; payout_amount: string; available: string }

const TONE: Record<Withdrawal['status'], 'default' | 'secondary' | 'destructive'> = {
  requested: 'secondary', paid: 'default', rejected: 'destructive', cancelled: 'secondary',
};
const SOURCE_LABEL: Record<Source, string> = { winnings: 'Winnings', deposit: 'Deposit' };
const input = 'w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-secondary';

/** Ask to be paid out: choose the wallet it comes from (Winnings, or Deposit
 *  at a much higher fee), see the amount, fee and what you'll receive, then
 *  confirm. Payouts are sent by the BetBlits team, so a request waits until
 *  they mark it paid. The server works out and records the fee. */
export function WithdrawPanel({ onChanged }: { onChanged: () => void }) {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<Mine>('/wallet/withdrawals/');
  const { data: wallets } = useWallets();
  const [source, setSource] = useState<Source | null>(null);
  const [amount, setAmount] = useState('');
  const [method, setMethod] = useState('ecocash');
  const [number, setNumber] = useState('');
  const [name, setName] = useState('');
  const [bank, setBank] = useState('');
  const [quote, setQuote] = useState<Quote | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);
  const isBank = method === 'bank';
  const limits = data?.limits;
  const feeFor: Record<Source, string | undefined> = { winnings: limits?.fee_percent, deposit: limits?.deposit_fee_percent };

  async function review(e: React.FormEvent) {
    e.preventDefault();
    if (!accessToken || !source) return;
    setBusy(true); setMsg(null);
    const res = await authedPost<Quote>('/wallet/withdraw/quote/', { amount, wallet: source }, accessToken);
    setBusy(false);
    if (res.error || !res.data) { setMsg({ ok: false, text: res.error ?? 'Could not work out the fee.' }); return; }
    setQuote(res.data);
  }

  async function confirmWithdrawal() {
    if (!accessToken || !quote) return;
    setBusy(true); setMsg(null);
    const { error } = await authedPost('/wallet/withdraw/', {
      amount: quote.amount, wallet: quote.wallet, method, account_number: number, account_name: name,
      ...(isBank ? { bank_name: bank } : {}),
    }, accessToken);
    setBusy(false);
    if (error) { setMsg({ ok: false, text: error }); setQuote(null); return; }
    setMsg({ ok: true, text: `Request sent — $${quote.amount} is on hold from your ${SOURCE_LABEL[quote.wallet]} wallet and `
      + `$${quote.payout_amount} will be paid to your ${data?.methods.find((m) => m.id === method)?.label ?? method} shortly.` });
    setQuote(null); setAmount('');
    refetch(); onChanged();
  }

  async function cancel(w: Withdrawal) {
    const where = SOURCE_LABEL[w.wallet ?? 'winnings'];
    if (!accessToken || !confirm(`Cancel this withdrawal? The money goes back to your ${where} wallet.`)) return;
    const { error } = await authedPost(`/wallet/withdrawals/${w.id}/cancel/`, {}, accessToken);
    setMsg(error ? { ok: false, text: error } : { ok: true, text: `Cancelled — the money is back in your ${where} wallet.` });
    refetch(); onChanged();
  }

  return (
    <div className="space-y-3">
      <p className="text-sm font-medium">Withdraw</p>
      {quote ? (
        <div className="space-y-3 rounded-xl border border-border p-4">
          <p className="text-sm font-semibold">Check before you confirm</p>
          <dl className="space-y-1.5 text-sm">
            <div className="flex justify-between"><dt className="text-muted-foreground">From</dt><dd className="font-semibold">{SOURCE_LABEL[quote.wallet]} wallet</dd></div>
            <div className="flex justify-between"><dt className="text-muted-foreground">Withdrawal amount</dt><dd className="font-semibold tabular-nums">${quote.amount}</dd></div>
            <div className="flex justify-between">
              <dt className="text-muted-foreground">Withdrawal fee ({Number(quote.fee_percent)}%)</dt>
              <dd className={`font-semibold tabular-nums ${quote.wallet === 'deposit' ? 'text-down' : ''}`}>−${quote.fee}</dd>
            </div>
            <div className="flex justify-between border-t border-border pt-1.5"><dt className="font-bold">You receive</dt><dd className="text-lg font-extrabold tabular-nums text-win">${quote.payout_amount}</dd></div>
          </dl>
          {quote.wallet === 'deposit' && (
            <p className="rounded-lg bg-down/10 px-3 py-2 text-xs font-semibold text-down">
              Withdrawing deposited money costs {Number(quote.fee_percent)}% — you lose ${quote.fee}. Winnings cost only {Number(limits?.fee_percent ?? 0)}%.
            </p>
          )}
          <div className="flex gap-2">
            <button onClick={() => setQuote(null)} disabled={busy} className="flex-1 rounded-md border border-border px-4 py-2 text-sm font-semibold">Back</button>
            <button onClick={() => void confirmWithdrawal()} disabled={busy}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-md bg-secondary px-4 py-2 text-sm font-bold text-secondary-foreground disabled:opacity-50">
              <FaArrowDown size={11} /> {busy ? 'Sending…' : `Confirm · receive $${quote.payout_amount}`}
            </button>
          </div>
        </div>
      ) : (
        <form onSubmit={review} className="grid gap-2 sm:grid-cols-2">
          <fieldset className="grid grid-cols-2 gap-2 sm:col-span-2">
            <legend className="mb-1 text-xs font-semibold text-muted-foreground">Withdraw from</legend>
            {(['winnings', 'deposit'] as Source[]).map((s) => (
              <button key={s} type="button" onClick={() => setSource(s)} aria-pressed={source === s}
                className={`rounded-lg border px-3 py-2 text-left ${source === s ? 'border-secondary bg-secondary/10' : 'border-border hover:bg-muted'}`}>
                <span className="block text-xs font-bold">{SOURCE_LABEL[s]} wallet</span>
                <span className="block text-sm font-extrabold tabular-nums">${Number(wallets?.wallets?.[s]?.balance ?? 0).toFixed(2)}</span>
                <span className={`block text-[11px] ${s === 'deposit' ? 'font-semibold text-down' : 'text-muted-foreground'}`}>
                  {feeFor[s] != null ? `${Number(feeFor[s])}% fee` : ''}
                </span>
              </button>
            ))}
          </fieldset>
          <input type="number" min="0" step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="Amount" aria-label="Amount" className={input} required />
          <select value={method} onChange={(e) => setMethod(e.target.value)} aria-label="Send to" className={input}>
            {(data?.methods ?? [{ id: 'ecocash', label: 'EcoCash' }]).map((m) => <option key={m.id} value={m.id}>{m.label}</option>)}
          </select>
          <input value={number} onChange={(e) => setNumber(e.target.value)} placeholder={isBank ? 'Account number' : 'Mobile number, e.g. 0771 234 567'}
            aria-label={isBank ? 'Account number' : 'Mobile number'} inputMode={isBank ? 'text' : 'tel'} className={input} required />
          <input value={name} onChange={(e) => setName(e.target.value)} placeholder="Name on the account" aria-label="Account name" className={input} required={isBank} />
          {isBank && <input value={bank} onChange={(e) => setBank(e.target.value)} placeholder="Bank, e.g. CBZ" aria-label="Bank" className={`${input} sm:col-span-2`} required />}
          <button type="submit" disabled={busy || !source || !amount || !number}
            className="flex items-center justify-center gap-1.5 rounded-md bg-secondary px-4 py-2 text-sm font-bold text-secondary-foreground disabled:opacity-50 sm:col-span-2">
            {busy ? 'Working out the fee…' : source ? 'Review withdrawal' : 'Choose a wallet to withdraw from'}
          </button>
        </form>
      )}
      <p className="text-xs text-muted-foreground">
        Bonus money can’t be withdrawn.
        {limits && <> Per request ${limits.min}–${limits.max}{limits.left_today ? `; $${limits.left_today} left today` : ''}. </>}
        The amount is held as soon as you ask and our team sends it — usually within a few hours.
        {source === 'winnings' && limits && Number(limits.turnover_left ?? 0) > 0 && (
          <b className="mt-1 block text-gold">Bet ${limits.turnover_left} more (sports or Aviator) to unlock withdrawals from Winnings.</b>
        )}
      </p>
      {msg && <p className={`text-sm ${msg.ok ? 'text-win' : 'text-down'}`}>{msg.text}</p>}

      {(data?.results ?? []).length > 0 && (
        <ul className="divide-y divide-border rounded-xl border border-border">
          {data!.results.map((w) => (
            <li key={w.id} className="flex flex-wrap items-center gap-x-3 gap-y-1 px-3 py-2 text-sm">
              <span className="font-semibold tabular-nums">${w.amount}</span>
              {Number(w.fee ?? 0) > 0 && <span className="text-xs text-muted-foreground">(${w.payout_amount} after ${w.fee} fee)</span>}
              {w.wallet && <span className="text-xs text-muted-foreground">from {SOURCE_LABEL[w.wallet]}</span>}
              <span className="text-muted-foreground">{w.legacy ? 'Earlier withdrawal — our team will contact you' : `${w.method_label} ${w.account_number}`}</span>
              <Badge variant={TONE[w.status]}>{w.status_label}</Badge>
              <span className="ml-auto text-xs text-muted-foreground">{new Date(w.created_at).toLocaleString()}</span>
              {w.status === 'requested' && (
                <button onClick={() => cancel(w)} className="text-xs font-semibold text-down hover:underline">Cancel</button>
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
