'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Input } from '@slyk/ui/components/input';
import { useAuth } from '@/lib/auth-context';
import { authedPost } from '@/lib/use-api';

export function BetSlip({ event = 'demo-event', initialOdds = 1.95 }: { event?: string; initialOdds?: number }) {
  const { user, accessToken } = useAuth();
  const [stake, setStake] = useState('10');
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const payout = (parseFloat(stake || '0') * initialOdds).toFixed(2);

  async function placeBet() {
    if (!accessToken) { setStatus('Please log in to place a bet.'); return; }
    setBusy(true); setStatus('Placing…');
    const { error } = await authedPost(
      '/bets/',
      { event, stake: Number(stake), odds: initialOdds },
      accessToken,
    );
    setStatus(error ? `Rejected: ${error}` : 'Bet placed ✅');
    setBusy(false);
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Bet Slip</CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <p className="text-sm text-muted-foreground">Event: <code>{event}</code></p>
        <p className="text-sm">Odds: <span className="font-semibold">{initialOdds}</span></p>
        <div className="space-y-1">
          <label className="text-xs text-muted-foreground">Stake</label>
          <Input value={stake} onChange={(e) => setStake(e.target.value)} inputMode="decimal" />
        </div>
        <p className="text-sm">Potential payout: <span className="font-semibold">{payout}</span></p>
        {user ? (
          <button
            className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
            onClick={placeBet}
            disabled={busy}
          >
            {busy ? 'Placing…' : 'Place Bet'}
          </button>
        ) : (
          <a
            href="/login"
            className="block w-full rounded-md bg-primary px-4 py-2 text-center text-sm font-medium text-primary-foreground hover:opacity-90"
          >
            Log in to bet
          </a>
        )}
        {status && <p className="text-sm text-muted-foreground">{status}</p>}
      </CardContent>
    </Card>
  );
}
