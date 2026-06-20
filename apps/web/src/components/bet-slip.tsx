'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { Input } from '@slyk/ui/components/input';
import { useAuth } from '@/lib/auth-context';
import { authedPost } from '@/lib/use-api';

const QUICK_STAKES = ['10', '25', '50', '100'];

export function BetSlip({ event = 'demo-event', initialOdds = 1.95, eventId, selection = 'home' }: {
  event?: string;
  initialOdds?: number;
  eventId?: string | number;
  selection?: string;
}) {
  const { user, accessToken } = useAuth();
  const [stake, setStake] = useState('10');
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const stakeNum = parseFloat(stake || '0');
  const payout = (stakeNum * initialOdds).toFixed(2);
  const profit = (stakeNum * (initialOdds - 1)).toFixed(2);

  async function placeBet() {
    if (!accessToken) { setStatus('Please log in to place a bet.'); return; }
    setBusy(true); setStatus('Placing…');
    const { error } = await authedPost(
      '/bets/',
      {
        event, stake: Number(stake), odds: initialOdds, selection,
        ...(eventId != null ? { event_id: Number(eventId) } : {}),
      },
      accessToken,
    );
    setStatus(error ? `Rejected: ${error}` : 'Bet placed.');
    setBusy(false);
  }

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0">
        <CardTitle>Bet Slip</CardTitle>
        <Badge variant="secondary">1 selection</Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex items-center justify-between rounded-md bg-muted/50 px-3 py-2">
          <p className="text-sm text-muted-foreground truncate">{event}</p>
          <Badge>{initialOdds}</Badge>
        </div>
        <div className="space-y-1.5">
          <label className="text-xs text-muted-foreground">Stake</label>
          <Input value={stake} onChange={(e) => setStake(e.target.value)} inputMode="decimal" />
          <div className="flex gap-1.5">
            {QUICK_STAKES.map((v) => (
              <button
                key={v}
                onClick={() => setStake(v)}
                className={`flex-1 rounded-md py-1 text-xs font-medium transition-colors ${
                  stake === v ? 'bg-primary text-primary-foreground' : 'bg-muted hover:bg-accent/10'
                }`}
              >
                {v}
              </button>
            ))}
          </div>
        </div>
        <div className="space-y-1 rounded-md border border-border px-3 py-2 text-sm">
          <div className="flex justify-between text-muted-foreground">
            <span>Potential profit</span>
            <span className="text-green-600 font-medium">+{profit}</span>
          </div>
          <div className="flex justify-between font-semibold">
            <span>Total payout</span>
            <span>{payout}</span>
          </div>
        </div>
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
