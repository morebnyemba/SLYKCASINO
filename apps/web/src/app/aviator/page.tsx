'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { BsInfoCircle } from 'react-icons/bs';
import { BetPanel } from '@/components/jet/bet-panel';
import { FlightScene } from '@/components/jet/flight-scene';
import { BetsList, HistoryStrip } from '@/components/jet/side-panels';
import { useAuth } from '@/lib/auth-context';
import { multiplierAt, useJet } from '@/lib/jet';

/** The game's wordmark: a small brand line over the big red italic title. */
function GameLogo({ name }: { name: string }) {
  const [brand, ...rest] = name.split(' ');
  const title = rest.length ? rest.join(' ') : brand;
  return (
    <span className="flex flex-col leading-none">
      {rest.length > 0 && <span className="text-[10px] font-extrabold uppercase tracking-[0.2em] text-white/70">{brand}</span>}
      <span className="text-[26px] font-black italic tracking-tight text-[#e50539] [text-shadow:0_2px_10px_rgba(229,5,57,0.45)]">{title}</span>
    </span>
  );
}

/** The multiplayer crash game (named in the admin; BetBlits Aviator by default). */
export default function AviatorPage() {
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
        {error ?? 'Loading…'}
      </div>
    );
  }

  const s = state.settings;
  const myBet = (slot: number) => state.my_bets.find((b) => b.slot === slot && b.round === round?.id);

  return (
    <div className="-mx-3 -mt-3 bg-[#0e0e0e] p-3 sm:mx-0 sm:mt-0 sm:rounded-3xl sm:border sm:border-[#2c2d30] lg:p-4">
      <header className="-mx-3 -mt-3 mb-3 flex items-center gap-3 border-b border-[#2c2d30] bg-[#1b1c1d] px-3 py-2 text-white sm:-mx-4 sm:-mt-4 sm:rounded-t-3xl sm:px-4">
        <GameLogo name={s.display_name} />
        {state.balance != null && (
          <span className="ml-auto text-base font-extrabold tabular-nums text-[#28a909]">
            {Number(state.balance).toFixed(2)} <span className="text-xs font-bold text-white/60">USD</span>
          </span>
        )}
        <button onClick={() => setRulesOpen((v) => !v)} aria-label="How to play"
          className={`${state.balance == null ? 'ml-auto' : ''} flex items-center gap-1.5 rounded-full bg-[#141516] px-3 py-1.5 text-xs font-bold text-white/80 hover:text-white`}>
          <BsInfoCircle size={13} /> How to play
        </button>
      </header>

      {rulesOpen && (
        <div className="mb-3 rounded-2xl border border-[#2c2d30] bg-[#1b1c1d] p-4 text-sm leading-relaxed text-white/80">
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
        <p className="mb-3 rounded-xl bg-[#f59e0b]/15 px-4 py-2.5 text-sm font-semibold text-[#fbbf24]">{s.display_name} is paused for a moment — bets will open again shortly.</p>
      )}
      {!user && (
        <p className="mb-3 rounded-xl bg-white/5 px-4 py-2.5 text-sm text-white/70">
          You’re watching. <Link href="/login" className="font-bold text-[#28a909] underline-offset-2 hover:underline">Log in</Link> to place bets.
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
