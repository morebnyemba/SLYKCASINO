'use client';

import Link from 'next/link';
import { use, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { useApi, authedPost } from '@/lib/use-api';

type PageProps = { params: Promise<{ slug: string }>; searchParams: Promise<{ id?: string }> };

interface SpinResult {
  win: string;
  balance: string;
  currency: string;
  round: { id: number; stake: string; win: string; status: string };
}

interface Wallet { balance?: string; currency?: string }

const REELS = ['🍒', '🍋', '🍊', '⭐', '💎', '🔔', '7️⃣', '🃏'];

function randomReel() {
  return REELS[Math.floor(Math.random() * REELS.length)];
}

function winLabel(win: string, stake: string): { text: string; color: string } {
  const w = parseFloat(win);
  const s = parseFloat(stake);
  if (w === 0) return { text: 'No win', color: 'text-muted-foreground' };
  const mult = w / s;
  if (mult >= 20) return { text: `JACKPOT! ${w.toFixed(2)} ×${mult.toFixed(0)}`, color: 'text-yellow-400' };
  if (mult >= 5) return { text: `BIG WIN! ${w.toFixed(2)} ×${mult.toFixed(0)}`, color: 'text-orange-400' };
  if (mult >= 2) return { text: `WIN ${w.toFixed(2)} ×${mult.toFixed(0)}`, color: 'text-green-400' };
  return { text: `Win ${w.toFixed(2)}`, color: 'text-green-600' };
}

export default function GamePage({ params, searchParams }: PageProps) {
  const { slug } = use(params);
  const { id: gameId } = use(searchParams);

  const { user, accessToken } = useAuth();
  const { data: wallet, refetch: refetchWallet } = useApi<Wallet>('/wallet/');

  const [stake, setStake] = useState('5');
  const [spinning, setSpinning] = useState(false);
  const [reels, setReels] = useState(['🎰', '🎰', '🎰']);
  const [result, setResult] = useState<SpinResult | null>(null);
  const [error, setError] = useState('');
  const [history, setHistory] = useState<SpinResult[]>([]);

  const gameName = slug.split('-').map((w) => w[0].toUpperCase() + w.slice(1)).join(' ');

  async function spin() {
    if (!accessToken || !gameId) return;
    setError('');
    setSpinning(true);
    setResult(null);

    // Animate reels while waiting
    const interval = setInterval(() => {
      setReels([randomReel(), randomReel(), randomReel()]);
    }, 80);

    const { data, error: err } = await authedPost<SpinResult>(
      `/casino/games/${gameId}/play/`,
      { stake: parseFloat(stake) },
      accessToken,
    );

    clearInterval(interval);
    setSpinning(false);

    if (err || !data) {
      setError(err ?? 'Spin failed');
      setReels(['❌', '❌', '❌']);
      return;
    }

    setResult(data);
    setHistory((h) => [data, ...h.slice(0, 9)]);
    refetchWallet();

    // Show win reels (same symbol = win feel)
    const win = parseFloat(data.win);
    if (win === 0) {
      setReels([randomReel(), randomReel(), randomReel()]);
    } else {
      const sym = REELS[Math.floor(Math.random() * REELS.length)];
      setReels([sym, sym, sym]);
    }
  }

  const balance = wallet?.balance ?? '0.00';
  const currency = wallet?.currency ?? 'USD';

  return (
    <div className="mx-auto max-w-lg">
      <div className="mb-4 flex items-center gap-2">
        <Link href="/casino" className="text-sm text-muted-foreground hover:text-foreground">← Casino</Link>
        <span className="text-muted-foreground">/</span>
        <span className="text-sm font-medium">{gameName}</span>
      </div>

      <Card className="overflow-hidden">
        <CardHeader className="bg-gradient-to-r from-purple-900/40 to-indigo-900/40 pb-4">
          <CardTitle className="text-center text-xl">{gameName}</CardTitle>
          <p className="text-center text-sm text-muted-foreground">
            Balance: <span className="font-bold text-foreground">{balance} {currency}</span>
          </p>
        </CardHeader>

        <CardContent className="space-y-6 pt-6">
          {/* Reels */}
          <div className="flex justify-center gap-3">
            {reels.map((sym, i) => (
              <div
                key={i}
                className={`flex h-20 w-20 items-center justify-center rounded-xl border-2 border-border bg-card text-4xl shadow-inner transition-all ${spinning ? 'animate-pulse border-primary' : ''}`}
              >
                {sym}
              </div>
            ))}
          </div>

          {/* Result */}
          <div className="min-h-8 text-center">
            {result && (() => {
              const { text, color } = winLabel(result.win, result.round.stake);
              return <p className={`text-lg font-bold ${color}`}>{text}</p>;
            })()}
            {error && <p className="text-sm text-destructive">{error}</p>}
          </div>

          {/* Stake + Spin */}
          <div className="space-y-3">
            <div className="flex items-center gap-3">
              <label className="w-12 text-sm text-muted-foreground">Stake</label>
              <div className="flex gap-2">
                {['1', '5', '10', '25', '50'].map((v) => (
                  <button
                    key={v}
                    onClick={() => setStake(v)}
                    className={`rounded-md px-3 py-1 text-sm font-medium transition-colors ${stake === v ? 'bg-primary text-primary-foreground' : 'bg-muted hover:bg-accent'}`}
                  >
                    {v}
                  </button>
                ))}
              </div>
            </div>

            {user ? (
              <button
                onClick={spin}
                disabled={spinning}
                className="w-full rounded-xl bg-primary py-4 text-lg font-bold text-primary-foreground transition-all hover:opacity-90 active:scale-95 disabled:opacity-50"
              >
                {spinning ? '⌛ Spinning…' : '🎰 SPIN'}
              </button>
            ) : (
              <Link
                href="/login"
                className="block w-full rounded-xl bg-primary py-4 text-center text-lg font-bold text-primary-foreground hover:opacity-90"
              >
                Log in to play
              </Link>
            )}
          </div>

          {/* Recent rounds */}
          {history.length > 0 && (
            <div>
              <p className="mb-2 text-xs font-medium text-muted-foreground uppercase tracking-wide">Recent spins</p>
              <div className="space-y-1">
                {history.map((h, i) => {
                  const w = parseFloat(h.win);
                  const s = parseFloat(h.round.stake);
                  return (
                    <div key={i} className="flex items-center justify-between rounded-md bg-muted/50 px-3 py-1.5 text-sm">
                      <span className="text-muted-foreground">Stake {h.round.stake} {h.currency}</span>
                      <Badge variant={w > 0 ? 'default' : 'secondary'}>
                        {w > 0 ? `+${h.win} (${(w/s).toFixed(1)}×)` : 'No win'}
                      </Badge>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
