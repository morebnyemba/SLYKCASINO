'use client';

import { useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Button } from '@slyk/ui/components/button';
import { Input } from '@slyk/ui/components/input';
import { config } from '@/lib/config';

export function BetSlip({ event = 'demo-event', initialOdds = 1.95 }: { event?: string; initialOdds?: number }) {
  const [stake, setStake] = useState('10');
  const [status, setStatus] = useState<string | null>(null);
  const payout = (parseFloat(stake || '0') * initialOdds).toFixed(2);

  async function placeBet() {
    setStatus('placing…');
    try {
      const res = await fetch(`${config.apiUrl}/bets/`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ event, stake: Number(stake), odds: initialOdds }),
      });
      setStatus(res.ok ? 'Bet placed ✅' : `Rejected (${res.status})`);
    } catch {
      setStatus('Backend unreachable (scaffold)');
    }
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
        <Button className="w-full" onClick={placeBet}>Place Bet</Button>
        {status && <p className="text-sm text-muted-foreground">{status}</p>}
      </CardContent>
    </Card>
  );
}
