'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { FaPlane } from 'react-icons/fa';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { useApi, authedPost } from '@/lib/use-api';
import { config } from '@/lib/config';

interface Wallet { balance?: string; currency?: string }

interface CrashRound {
  id: number;
  stake: string;
  status: 'running' | 'cashed' | 'busted';
  cashout_multiplier: string | null;
  win: string;
  nonce: number;
  server_seed_hash: string;
  server_seed: string | null;
  crash_point: string | null;
  growth_rate: number;
  created_at: string;
}

interface CashoutResult {
  round: CrashRound;
  balance: string;
  currency: string;
}

interface HistoryItem { id: number; crash_point: string; created_at: string }

// Force resolution if a player never cashes out — submits a cash-out once the
// on-screen multiplier is high enough that it has almost certainly busted.
const CEILING_MULTIPLIER = 1000;

function multColor(m: number): string {
  if (m >= 10) return 'text-yellow-400';
  if (m >= 2) return 'text-green-400';
  return 'text-foreground';
}

export default function CrashPage() {
  const { user, accessToken } = useAuth();
  const { data: wallet, refetch: refetchWallet } = useApi<Wallet>('/wallet/');

  const [stake, setStake] = useState('5');
  const [autoCashout, setAutoCashout] = useState('');
  const [round, setRound] = useState<CrashRound | null>(null);
  const [multiplier, setMultiplier] = useState(1);
  const [phase, setPhase] = useState<'idle' | 'running' | 'settled'>('idle');
  const [result, setResult] = useState<CrashRound | null>(null);
  const [error, setError] = useState('');
  const [history, setHistory] = useState<HistoryItem[]>([]);

  const rafRef = useRef<number | null>(null);
  const startRef = useRef<number>(0);
  const roundRef = useRef<CrashRound | null>(null);
  const cashingRef = useRef(false);

  const loadHistory = useCallback(async () => {
    try {
      const res = await fetch(`${config.apiUrl}/casino/crash/history/`, { cache: 'no-store' });
      if (res.ok) setHistory((await res.json()) as HistoryItem[]);
    } catch { /* ignore */ }
  }, []);

  useEffect(() => { void loadHistory(); }, [loadHistory]);

  const stopLoop = useCallback(() => {
    if (rafRef.current !== null) cancelAnimationFrame(rafRef.current);
    rafRef.current = null;
  }, []);

  const doCashout = useCallback(async (target?: number) => {
    const current = roundRef.current;
    if (!current || !accessToken || cashingRef.current) return;
    cashingRef.current = true;
    stopLoop();

    const body = target != null ? { multiplier: target.toFixed(2) } : {};
    const { data, error: err } = await authedPost<CashoutResult>(
      `/casino/crash/${current.id}/cashout/`, body, accessToken,
    );
    cashingRef.current = false;

    if (err || !data) { setError(err ?? 'Cash-out failed'); setPhase('idle'); setRound(null); roundRef.current = null; return; }

    setResult(data.round);
    setPhase('settled');
    setRound(null);
    roundRef.current = null;
    refetchWallet();
    void loadHistory();
  }, [accessToken, stopLoop, refetchWallet, loadHistory]);

  const tick = useCallback(() => {
    const current = roundRef.current;
    if (!current) return;
    const elapsed = (performance.now() - startRef.current) / 1000;
    const m = Math.exp(current.growth_rate * elapsed);
    setMultiplier(m);

    const auto = parseFloat(autoCashout);
    if (!Number.isNaN(auto) && auto >= 1.01 && m >= auto) { void doCashout(auto); return; }
    if (m >= CEILING_MULTIPLIER) { void doCashout(); return; }

    rafRef.current = requestAnimationFrame(tick);
  }, [autoCashout, doCashout]);

  async function placeBet() {
    if (!accessToken) return;
    setError('');
    setResult(null);
    const { data, error: err } = await authedPost<CrashRound>(
      '/casino/crash/', { stake: parseFloat(stake) }, accessToken,
    );
    if (err || !data) { setError(err ?? 'Could not place bet'); return; }

    setRound(data);
    roundRef.current = data;
    setMultiplier(1);
    setPhase('running');
    startRef.current = performance.now();
    refetchWallet();
    rafRef.current = requestAnimationFrame(tick);
  }

  useEffect(() => () => stopLoop(), [stopLoop]);

  const balance = wallet?.balance ?? '0.00';
  const currency = wallet?.currency ?? 'USD';
  const liveColor = multColor(multiplier);

  return (
    <div className="mx-auto max-w-lg">
      <div className="mb-4 flex items-center gap-2">
        <Link href="/casino" className="text-sm text-muted-foreground hover:text-foreground">← Casino</Link>
        <span className="text-muted-foreground">/</span>
        <span className="text-sm font-medium">SLYK Aviator</span>
      </div>

      {/* Recent crash multipliers */}
      {history.length > 0 && (
        <div className="mb-4 flex gap-1.5 overflow-x-auto pb-1">
          {history.map((h) => {
            const m = parseFloat(h.crash_point);
            return (
              <span
                key={h.id}
                className={`shrink-0 rounded-md px-2 py-1 text-xs font-mono font-semibold ${
                  m >= 10 ? 'bg-yellow-400/15 text-yellow-400'
                    : m >= 2 ? 'bg-green-500/15 text-green-500'
                    : 'bg-red-500/15 text-red-500'
                }`}
              >
                {m.toFixed(2)}×
              </span>
            );
          })}
        </div>
      )}

      <Card className="overflow-hidden">
        <CardHeader className="bg-gradient-to-r from-primary/30 to-secondary/30 pb-4">
          <CardTitle className="text-center text-xl">SLYK Aviator</CardTitle>
          <p className="text-center text-sm text-muted-foreground">
            Balance: <span className="font-bold text-foreground">{balance} {currency}</span>
          </p>
        </CardHeader>

        <CardContent className="space-y-6 pt-6">
          {/* Multiplier stage */}
          <div className="relative flex h-44 items-center justify-center overflow-hidden rounded-xl border-2 border-border bg-card">
            {phase === 'running' && (
              <FaPlane
                className="absolute text-primary transition-none"
                size={28}
                style={{
                  left: `${Math.min(85, 8 + multiplier * 6)}%`,
                  bottom: `${Math.min(80, 8 + multiplier * 5)}%`,
                }}
              />
            )}
            <div className="text-center">
              {phase === 'settled' && result?.status === 'busted' ? (
                <p className="text-4xl font-extrabold text-red-500">
                  BUSTED @ {parseFloat(result.crash_point ?? '0').toFixed(2)}×
                </p>
              ) : phase === 'settled' && result?.status === 'cashed' ? (
                <p className="text-4xl font-extrabold text-green-400">
                  +{result.win} {currency}
                </p>
              ) : (
                <p className={`font-mono text-5xl font-extrabold ${liveColor}`}>
                  {multiplier.toFixed(2)}×
                </p>
              )}
              {phase === 'settled' && result?.status === 'cashed' && (
                <p className="mt-1 text-sm text-muted-foreground">
                  Cashed out at {parseFloat(result.cashout_multiplier ?? '0').toFixed(2)}×
                </p>
              )}
            </div>
          </div>

          {error && <p className="text-center text-sm text-destructive">{error}</p>}

          {/* Controls */}
          {phase === 'running' ? (
            <button
              onClick={() => doCashout(multiplier)}
              className="w-full rounded-xl bg-secondary py-4 text-lg font-bold text-white transition-all hover:opacity-90 active:scale-95"
            >
              Cash Out {multiplier.toFixed(2)}× ({(parseFloat(stake) * multiplier).toFixed(2)} {currency})
            </button>
          ) : (
            <div className="space-y-3">
              <div className="flex items-center gap-3">
                <label className="w-20 text-sm text-muted-foreground">Stake</label>
                <div className="flex flex-wrap gap-2">
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
              <div className="flex items-center gap-3">
                <label className="w-20 text-sm text-muted-foreground">Auto cash-out</label>
                <input
                  type="number"
                  step="0.1"
                  min="1.01"
                  value={autoCashout}
                  onChange={(e) => setAutoCashout(e.target.value)}
                  placeholder="e.g. 2.00 (optional)"
                  className="flex-1 rounded-md border border-border bg-background px-3 py-1.5 text-sm"
                />
              </div>

              {user ? (
                <button
                  onClick={placeBet}
                  className="w-full rounded-xl bg-primary py-4 text-lg font-bold text-primary-foreground transition-all hover:opacity-90 active:scale-95"
                >
                  Place bet
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
          )}

          {/* Provably fair */}
          {result && (
            <details className="rounded-md border border-border p-3 text-xs text-muted-foreground">
              <summary className="cursor-pointer select-none font-medium">Provably fair</summary>
              <div className="mt-2 space-y-1 break-all font-mono">
                <p>Crash point: <span className="text-foreground">{result.crash_point}×</span></p>
                <p>Nonce: {result.nonce}</p>
                <p>Seed hash: {result.server_seed_hash}</p>
                <p>Server seed: {result.server_seed ?? '—'}</p>
                <p className="font-sans not-italic">
                  Verify: <code>HMAC_SHA256(server_seed, nonce)</code> derives the crash point; the seed
                  hash was committed before the round.
                </p>
              </div>
            </details>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
