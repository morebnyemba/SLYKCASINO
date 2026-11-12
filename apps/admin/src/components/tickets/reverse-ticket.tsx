'use client';

import { useState } from 'react';
import { Btn, Field, Notice, Select, TextInput, money } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost } from '@/lib/use-api';

export interface Reversal {
  outcome: 'lost' | 'void'; paid: string; owed: string; recovered: string; shortfall: string;
  taken: Record<string, string>; reason: string; reversed_by: string; created_at: string;
}
interface Plan { owed: string; recovered: string; shortfall: string; take: Record<string, string> }

const WALLET: Record<string, string> = { winnings: 'Winnings', deposit: 'Deposit', bonus: 'Bonus' };
const taken = (t: Record<string, string>) => Object.entries(t).map(([b, v]) => `${money(v)} from ${WALLET[b] ?? b}`).join(', ');

/** A reversal already made on this ticket. */
export function ReversalNote({ r }: { r: Reversal }) {
  return (
    <div className="rounded-2xl border border-live/40 bg-live/5 p-4 text-sm">
      <p className="font-bold text-live">Winnings reversed — corrected to {r.outcome}</p>
      <p className="mt-1 text-xs text-muted-foreground">
        {money(r.recovered)} of {money(r.owed)} taken back{Object.keys(r.taken).length > 0 && ` (${taken(r.taken)})`}
        {Number(r.shortfall) > 0 && <> · <b className="text-live">{money(r.shortfall)} still owed</b> (already withdrawn or bet)</>}.
      </p>
      <p className="mt-1 text-xs text-muted-foreground">{r.reason} — {r.reversed_by}, {new Date(r.created_at).toLocaleString()}</p>
    </div>
  );
}

/** Superuser: take back the winnings of a ticket settled as won by mistake. Reviews first, then confirms. */
export function ReverseTicket({ ticket, onDone }: { ticket: string; onDone: () => void }) {
  const { accessToken } = useAuth();
  const [open, setOpen] = useState(false);
  const [outcome, setOutcome] = useState<'lost' | 'void'>('lost');
  const [reason, setReason] = useState('');
  const [plan, setPlan] = useState<Plan | null>(null);
  const [freeze, setFreeze] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const url = `/admin/tickets/${ticket}/reverse/`;

  async function review(next = outcome) {
    if (!accessToken) return;
    setBusy(true); setError('');
    const res = await authedPost<Plan>(url, { outcome: next, dry_run: true }, accessToken);
    setBusy(false);
    if (res.error || !res.data) { setPlan(null); setError(res.error ?? 'Could not check this ticket.'); return; }
    setPlan(res.data);
  }
  async function reverse() {
    if (!accessToken || !plan) return;
    const short = Number(plan.shortfall) > 0;
    setBusy(true); setError('');
    const res = await authedPost(url, { outcome, reason, accept_shortfall: short, freeze_withdrawals: short && freeze }, accessToken);
    setBusy(false);
    if (res.error) { setError(res.error); return; }
    onDone();
  }

  if (!open) {
    return <Btn size="sm" variant="danger" onClick={() => { setOpen(true); void review(); }}>Reverse winnings…</Btn>;
  }
  const short = plan && Number(plan.shortfall) > 0;
  return (
    <div className="space-y-3 rounded-2xl border border-live/40 bg-live/5 p-4 text-sm">
      <p className="font-bold text-live">Reverse this ticket’s winnings</p>
      <p className="text-xs text-muted-foreground">For a ticket settled as won by mistake. The money is taken back from the player’s wallets and the ticket is re-marked. It can be done once and can’t be undone.</p>
      <Field label="The ticket should have been">
        <Select value={outcome} onChange={(e) => { const v = e.target.value as 'lost' | 'void'; setOutcome(v); void review(v); }}>
          <option value="lost">Lost — take back the payout and the returned stake</option>
          <option value="void">Void — take back the winnings, the stake stays returned</option>
        </Select>
      </Field>
      {plan && (
        <div className="rounded-xl bg-card p-3 text-xs">
          <p><b>{money(plan.owed)}</b> to take back · the player holds <b>{money(plan.recovered)}</b> of it{Object.keys(plan.take).length > 0 && ` (${taken(plan.take)})`}.</p>
          {short && (
            <>
              <p className="mt-1 font-semibold text-live">{money(plan.shortfall)} has already been withdrawn or bet. It will be recorded as owed; a wallet never goes below zero.</p>
              <label className="mt-2 flex items-center gap-2">
                <input type="checkbox" checked={freeze} onChange={(e) => setFreeze(e.target.checked)} className="h-4 w-4" />
                Freeze this player’s withdrawals until the rest is settled
              </label>
            </>
          )}
        </div>
      )}
      <Field label="Reason" hint="Kept with the ticket and in the audit log.">
        <TextInput value={reason} onChange={(e) => setReason(e.target.value)} maxLength={300} placeholder="Result entered as 2-1, the match ended 1-2" />
      </Field>
      {error && <Notice tone="red" onClose={() => setError('')}>{error}</Notice>}
      <div className="flex flex-wrap justify-end gap-2">
        <Btn size="sm" variant="ghost" onClick={() => setOpen(false)} disabled={busy}>Cancel</Btn>
        <Btn size="sm" variant="danger" busy={busy} disabled={!plan || reason.trim().length < 5} onClick={reverse}>
          {plan ? `Take back ${money(plan.recovered)} and mark ${outcome}` : 'Reverse'}
        </Btn>
      </div>
    </div>
  );
}
