'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';

interface RefundInfo { deposit_balance: string; destinations: string[]; reasons: Record<string, string> }

const input = 'w-full rounded-md border border-border bg-background px-3 py-2 text-sm focus:outline-none focus:ring-2 focus:ring-primary';

/** Return unplayed Deposit-wallet money — only when the player self-excludes
 *  or their account is closed (suspended), only to a number their deposits came
 *  from, and only after you've sent it (enter the transaction reference). */
export function DepositRefund({ playerId, onDone }: { playerId: number; onDone: () => void }) {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<RefundInfo>(`/admin/players/${playerId}/deposit-refund/`);
  const [amount, setAmount] = useState('');
  const [reason, setReason] = useState('self_exclusion');
  const [destination, setDestination] = useState('');
  const [reference, setReference] = useState('');
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  if (!data || Number(data.deposit_balance) <= 0) return null;

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!accessToken) return;
    if (!window.confirm(`Record a $${Number(amount).toFixed(2)} deposit refund to ${destination}? Only do this after you've sent it.`)) return;
    setBusy(true); setMsg(null);
    const res = await authedPost<{ transaction_ref: string }>(`/admin/players/${playerId}/deposit-refund/`,
      { amount, reason, destination, reference }, accessToken);
    setBusy(false);
    if (res.error) { setMsg({ ok: false, text: res.error }); return; }
    setMsg({ ok: true, text: `Recorded as ${res.data?.transaction_ref}.` });
    setAmount(''); setReference('');
    refetch(); onDone();
  }

  return (
    <Card className="overflow-hidden rounded-2xl border-border/70">
      <CardHeader><CardTitle className="text-base">Refund unplayed deposits</CardTitle></CardHeader>
      <CardContent className="space-y-3">
        <p className="text-xs text-muted-foreground">
          Deposit money is never withdrawable by the player. It can only come back here, when they self-exclude
          or their account is closed (suspend it first), and only to a number their deposits came from.
          Send the money first, then record it with the transaction reference. Deposit wallet: <b>${data.deposit_balance}</b>.
        </p>
        {data.destinations.length === 0 ? (
          <p className="text-sm text-muted-foreground">No deposit number on record for this player, so a refund can’t be recorded here.</p>
        ) : (
          <form onSubmit={submit} className="grid gap-2 sm:grid-cols-2">
            <input type="number" min="0" step="0.01" max={data.deposit_balance} value={amount}
              onChange={(e) => setAmount(e.target.value)} placeholder="Amount" aria-label="Amount" className={input} required />
            <select value={reason} onChange={(e) => setReason(e.target.value)} aria-label="Reason" className={input}>
              {Object.entries(data.reasons).map(([id, label]) => <option key={id} value={id}>{label}</option>)}
            </select>
            <select value={destination} onChange={(e) => setDestination(e.target.value)} aria-label="Send to" className={input} required>
              <option value="" disabled>Deposit number…</option>
              {data.destinations.map((d) => <option key={d} value={d}>{d}</option>)}
            </select>
            <input value={reference} onChange={(e) => setReference(e.target.value)} placeholder="EcoCash/bank reference"
              aria-label="Reference" className={input} required />
            <button type="submit" disabled={busy}
              className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50 sm:col-span-2">
              {busy ? 'Recording…' : 'Record refund'}
            </button>
          </form>
        )}
        {msg && <p className={`text-sm ${msg.ok ? 'text-win' : 'text-destructive'}`}>{msg.text}</p>}
      </CardContent>
    </Card>
  );
}
