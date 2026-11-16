'use client';

import { useState } from 'react';
import { BsStars } from 'react-icons/bs';
import { useAuth } from '@/lib/auth-context';
import { authedPost } from '@/lib/use-api';

export interface BonusAviatorStatus { stake: string; profit: string; max_to_winnings: string }

/**
 * Profit from Aviator bonus bets ($0.10 stakes from the Bonus wallet, profit
 * only), waiting to be claimed: into Deposit (any amount) or Winnings (up to
 * the bonus limit). Hidden while there's nothing to claim.
 */
export function BonusProfitCard({ status, onClaimed }: { status?: BonusAviatorStatus | null; onClaimed: () => void }) {
  const { accessToken } = useAuth();
  const [busy, setBusy] = useState<'' | 'deposit' | 'winnings'>('');
  const [note, setNote] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null);
  if (!status || Number(status.profit) <= 0) {
    return note ? <p className={`text-sm font-semibold ${note.tone === 'ok' ? 'text-win' : 'text-red-500'}`}>{note.text}</p> : null;
  }
  const profit = Number(status.profit);
  const toWinnings = Number(status.max_to_winnings);

  async function claim(to: 'deposit' | 'winnings') {
    if (!accessToken) return;
    setBusy(to); setNote(null);
    const res = await authedPost<{ claimed: string }>('/wallet/bonus-profit/claim/', { to }, accessToken);
    setBusy('');
    if (res.error) { setNote({ tone: 'err', text: res.error }); return; }
    setNote({ tone: 'ok', text: `$${Number(res.data?.claimed ?? 0).toFixed(2)} moved to your ${to === 'deposit' ? 'Deposit' : 'Winnings'} wallet.` });
    onClaimed();
  }

  return (
    <div className="rounded-2xl border border-secondary/40 bg-secondary/5 p-4">
      <div className="flex flex-wrap items-center gap-3">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-secondary/15 text-secondary"><BsStars size={18} /></span>
        <div className="min-w-0 flex-1">
          <p className="text-sm font-extrabold">Aviator bonus profit: <span className="tabular-nums text-secondary">${profit.toFixed(2)}</span></p>
          <p className="text-xs text-muted-foreground">
            From your ${Number(status.stake).toFixed(2)} bonus bets. Claim it to Deposit (any amount), or to Winnings
            {toWinnings > 0 ? <> — up to <b>${toWinnings.toFixed(2)}</b> right now</> : <> — your Winnings bonus limit is reached</>}.
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button disabled={!!busy} onClick={() => claim('deposit')}
            className="h-10 rounded-xl bg-secondary px-4 text-sm font-bold text-secondary-foreground disabled:opacity-60">
            {busy === 'deposit' ? 'Moving…' : 'To Deposit'}
          </button>
          <button disabled={!!busy || toWinnings <= 0} onClick={() => claim('winnings')}
            className="h-10 rounded-xl border border-secondary px-4 text-sm font-bold text-secondary disabled:opacity-40">
            {busy === 'winnings' ? 'Moving…' : 'To Winnings'}
          </button>
        </div>
      </div>
      {note && <p className={`mt-2 text-sm font-semibold ${note.tone === 'ok' ? 'text-win' : 'text-red-500'}`}>{note.text}</p>}
    </div>
  );
}
