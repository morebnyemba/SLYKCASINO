'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { BsInfoCircle } from 'react-icons/bs';
import { BetPanel } from '@/components/jet/bet-panel';
import { FlightScene } from '@/components/jet/flight-scene';
import { BetsList, HistoryStrip } from '@/components/jet/side-panels';
import { useAuth } from '@/lib/auth-context';
import { multiplierAt, useJet } from '@/lib/jet';

/** Jet — the multiplayer crash game. */
export default function JetPage() {
  const { user } = useAuth();
  const { state, error, now, placeBet, cancelBet, cashOut } = useJet();
  const [multiplier, setMultiplier] = useState(1);
  const [rulesOpen, setRulesOpen] = useState(false);

  // Live multiplier for the cash-out buttons (10 times a second while flying).
  const round = state?.round ?? null;
  const rate = state?.settings.rate ?? 0.1;
  useEffect(() => {
    if (round?.status !== 'flying' || !round.started_at) return;
    const start = Date.parse(round.started_at);
    const timer = window.setInterval(() => setMultiplier(multiplierAt((now() - start) / 1000, rate)), 100);
    return () => window.clearInterval(timer);
  }, [round?.status, round?.started_at, now, rate]);

  if (!state) {
    return (
      <div className="flex h-[60vh] items-center justify-center text-sm text-muted-foreground">
        {error ?? 'Loading Jet…'}
      </div>
    );
  }

  const s = state.settings;
  const myBet = (slot: number) => state.my_bets.find((b) => b.slot === slot && b.round === round?.id);

  return (
    <div className="-mx-3 -mt-3 bg-[#0e0a1c] p-3 sm:mx-0 sm:mt-0 sm:rounded-3xl lg:p-4">
      <header className="mb-3 flex items-center gap-3 text-white">
        <h1 className="text-xl font-black italic tracking-tight">
          <span className="text-[#ff3b6b]">Jet</span>
        </h1>
        <span className="rounded-full bg-white/10 px-2 py-0.5 text-[11px] font-bold text-white/70">RTP {Number(s.rtp_percent).toFixed(0)}%</span>
        {state.balance != null && (
          <span className="ml-auto rounded-full bg-black/40 px-3 py-1 text-sm font-extrabold tabular-nums text-[#22c55e]">
            ${Number(state.balance).toFixed(2)}
          </span>
        )}
        <button onClick={() => setRulesOpen((v) => !v)} aria-label="How to play"
          className={`${state.balance == null ? 'ml-auto' : ''} rounded-full p-2 text-white/70 hover:bg-white/10`}>
          <BsInfoCircle size={16} />
        </button>
      </header>

      {rulesOpen && (
        <div className="mb-3 rounded-2xl border border-white/10 bg-[#1b1530] p-4 text-sm leading-relaxed text-white/80">
          <p className="mb-2 font-bold text-white">How to play</p>
          <ol className="list-decimal space-y-1 pl-5">
            <li>Place one or two bets during the countdown.</li>
            <li>The plane takes off and the multiplier climbs.</li>
            <li>Cash out before it flies away to win your stake × the multiplier. Still riding when it flies away? The bet is lost.</li>
          </ol>
          <p className="mt-2 text-white/60">
            Bets {`$${s.min_bet}`}–{`$${s.max_bet}`} · max win ${Number(s.max_win).toLocaleString()} per bet (paid automatically when reached) ·
            the plane can reach up to {Number(s.max_multiplier).toLocaleString()}x · return to player {s.rtp_percent}%.
            Every round is provably fair — tap any result above the game to check it.
          </p>
        </div>
      )}

      {!s.enabled && (
        <p className="mb-3 rounded-xl bg-[#f59e0b]/15 px-4 py-2.5 text-sm font-semibold text-[#fbbf24]">Jet is paused for a moment — bets will open again shortly.</p>
      )}
      {!user && (
        <p className="mb-3 rounded-xl bg-white/5 px-4 py-2.5 text-sm text-white/70">
          You’re watching. <Link href="/login" className="font-bold text-[#22c55e] underline-offset-2 hover:underline">Log in</Link> to place bets.
        </p>
      )}

      <div className="grid grid-cols-1 gap-3 lg:grid-cols-[300px_minmax(0,1fr)]">
        <div className="order-2 h-[360px] lg:order-1 lg:h-auto">
          <BetsList bets={state.bets} loggedIn={!!user} />
        </div>
        <div className="order-1 min-w-0 space-y-3 lg:order-2">
          <HistoryStrip history={state.history} settings={s} />
          <FlightScene round={round} rate={rate} bettingSeconds={s.betting_seconds} now={now} />
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {[1, 2].map((slot) => (
              <BetPanel
                key={slot} slot={slot} settings={s} round={round} bet={myBet(slot)} multiplier={multiplier}
                loggedIn={!!user}
                onPlace={(stake, auto) => placeBet(slot, stake, auto)}
                onCancel={cancelBet}
                onCashOut={cashOut}
              />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
