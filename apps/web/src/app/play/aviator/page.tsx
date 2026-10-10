'use client';

import { useEffect, useRef, useState } from 'react';
import { BsChatDotsFill, BsInfoCircle, BsMusicNoteBeamed, BsVolumeMuteFill, BsVolumeUpFill } from 'react-icons/bs';
import { BetPanel } from '@/components/jet/bet-panel';
import { ChatPanel } from '@/components/jet/chat-panel';
import { FlightScene } from '@/components/jet/flight-scene';
import { BetsList, HistoryStrip } from '@/components/jet/side-panels';
import { useAuth } from '@/lib/auth-context';
import { multiplierAt, useJet, useJetChat, type JetBet, type JetRound } from '@/lib/jet';
import * as sound from '@/lib/jet-sound';

/** Plays the game's sounds from state changes: take-off, engine, countdown, crash and the player's cash-outs. */
function useGameSounds(round: JetRound | null, multiplier: number, myBets: JetBet[], now: () => number) {
  const lastStatus = useRef<string | null>(null);
  const cashed = useRef<Set<number> | null>(null);
  const [toast, setToast] = useState<{ key: number; x: string; win: string } | null>(null);

  // Audio may only start after the player touches the page.
  useEffect(() => {
    const unlock = () => sound.unlockSound();
    window.addEventListener('pointerdown', unlock);
    window.addEventListener('keydown', unlock);
    return () => {
      window.removeEventListener('pointerdown', unlock);
      window.removeEventListener('keydown', unlock);
      sound.stopEngine();
      sound.stopMusic();
    };
  }, []);

  // The music lifts while the plane is in the air.
  useEffect(() => { sound.setMusicEnergy(round?.status === 'flying' ? 1 : 0); }, [round?.status]);

  useEffect(() => {
    const status = round?.status ?? null;
    const prev = lastStatus.current;
    lastStatus.current = status;
    if (prev === null) { if (status === 'flying') sound.startEngine(); return; }
    if (status === prev) return;
    if (status === 'flying') sound.startEngine();
    else if (status === 'crashed') sound.playCrash();
    else sound.stopEngine();
  }, [round?.status, round?.id]);

  useEffect(() => { if (round?.status === 'flying') sound.updateEngine(multiplier); }, [multiplier, round?.status]);

  // Ticks over the last three seconds of the countdown.
  useEffect(() => {
    if (round?.status !== 'betting') return;
    const ends = Date.parse(round.betting_ends_at);
    let last = -1;
    const timer = window.setInterval(() => {
      const left = Math.ceil((ends - now()) / 1000);
      if (left >= 1 && left <= 3 && left !== last) { last = left; sound.playTick(); }
    }, 100);
    return () => window.clearInterval(timer);
  }, [round?.status, round?.betting_ends_at, now]);

  // Chime once per bet that cashes out — by tap, auto cash-out or the max-win cap.
  useEffect(() => {
    const done = myBets.filter((b) => b.status === 'cashed').map((b) => b.id);
    if (cashed.current === null) { cashed.current = new Set(done); return; }
    for (const id of done) {
      if (!cashed.current.has(id)) {
        cashed.current.add(id);
        sound.playCashout();
        const b = myBets.find((x) => x.id === id)!;
        setToast({ key: id, x: Number(b.cashout_multiplier ?? 0).toFixed(2), win: Number(b.payout).toFixed(2) });
      }
    }
  }, [myBets]);

  useEffect(() => {
    if (!toast) return;
    const t = window.setTimeout(() => setToast(null), 3200);
    return () => window.clearTimeout(t);
  }, [toast]);

  return toast;
}

/** Aviator's green "You have cashed out!" banner over the game screen. */
function CashoutToast({ toast }: { toast: { key: number; x: string; win: string } | null }) {
  if (!toast) return null;
  return (
    <div className="pointer-events-none absolute inset-x-0 top-3 z-10 flex justify-center px-3">
      <div key={toast.key} className="flex animate-[jet-toast_3.2s_ease-in-out_forwards] items-center gap-4 rounded-full border border-[#4ce42e]/60 bg-gradient-to-r from-[#123d0b] to-[#1d6110] py-1.5 pl-5 pr-1.5 text-white shadow-[0_8px_30px_rgba(40,169,9,0.45)]">
        <span className="leading-tight">
          <span className="block text-[11px] font-semibold text-white/75">You have cashed out!</span>
          <span className="text-xl font-black tabular-nums">{toast.x}x</span>
        </span>
        <span className="rounded-full bg-[#28a909] px-4 py-1.5 text-center leading-tight">
          <span className="block text-[10px] font-semibold uppercase text-white/80">Win, USD</span>
          <span className="text-lg font-black tabular-nums">{toast.win}</span>
        </span>
      </div>
    </div>
  );
}

function SoundToggles() {
  const [sfx, setSfx] = useState(true);
  const [music, setMusic] = useState(true);
  useEffect(() => { setSfx(sound.soundEnabled()); setMusic(sound.musicEnabled()); }, []);
  const cls = 'relative flex h-8 w-8 items-center justify-center rounded-full bg-[#141516] hover:text-white';
  return (
    <>
      <button onClick={() => { sound.setSoundEnabled(!sfx); setSfx(!sfx); }} aria-label={sfx ? 'Mute sound' : 'Turn sound on'} title={sfx ? 'Sound: on' : 'Sound: off'}
        className={`${cls} ${sfx ? 'text-white/85' : 'text-white/35'}`}>
        {sfx ? <BsVolumeUpFill size={15} /> : <BsVolumeMuteFill size={15} />}
      </button>
      <button onClick={() => { sound.setMusicEnabled(!music); setMusic(!music); }} aria-label={music ? 'Turn music off' : 'Turn music on'} title={music ? 'Music: on' : 'Music: off'}
        className={`${cls} ${music ? 'text-white/85' : 'text-white/35'}`}>
        <BsMusicNoteBeamed size={14} />
        {!music && <span className="absolute h-[1.5px] w-5 rotate-45 rounded bg-current" />}
      </button>
    </>
  );
}

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

const EMPTY: JetBet[] = [];

/** The multiplayer crash game (named in the admin; BetBlits Aviator by default). */
export default function AviatorPage() {
  const { user } = useAuth();
  const { state, error, now, placeBet, cancelBet, cashOut } = useJet();
  const [multiplier, setMultiplier] = useState(1);
  const [rulesOpen, setRulesOpen] = useState(false);
  const chat = useJetChat();
  const [chatOpen, setChatOpen] = useState(false);
  const [seen, setSeen] = useState(0);
  const lastChat = chat.messages[chat.messages.length - 1]?.id ?? 0;
  // Messages that arrived while the chat drawer was closed (small screens).
  useEffect(() => { if (chatOpen) setSeen(lastChat); }, [chatOpen, lastChat]);
  const unread = !chatOpen && lastChat > seen && seen > 0;
  useEffect(() => { if (seen === 0 && lastChat) setSeen(lastChat); }, [lastChat, seen]);

  // Live multiplier for the cash-out buttons (10 times a second while flying).
  const round = state?.round ?? null;
  const rate = state?.settings.rate ?? 0.1;
  useEffect(() => {
    if (round?.status !== 'flying' || !round.started_at) return;
    const start = Date.parse(round.started_at);
    const timer = window.setInterval(() => setMultiplier(multiplierAt((now() - start) / 1000, rate)), 100);
    return () => window.clearInterval(timer);
  }, [round?.status, round?.started_at, now, rate]);

  const toast = useGameSounds(round, multiplier, state?.my_bets ?? EMPTY, now);

  if (!state) {
    return (
      <div className="flex min-h-dvh items-center justify-center bg-[#0e0e0e] text-sm text-white/60">
        {error ?? 'Loading…'}
      </div>
    );
  }

  const s = state.settings;
  const myBet = (slot: number) => state.my_bets.find((b) => b.slot === slot && b.round === round?.id);

  return (
    <div className="min-h-dvh bg-[#0e0e0e] p-2 sm:p-3">
      <header className="-mx-2 -mt-2 mb-2 flex items-center gap-3 border-b border-[#2c2d30] bg-[#1b1c1d] px-3 py-2 text-white sm:-mx-3 sm:-mt-3 sm:mb-3">
        <GameLogo name={s.display_name} />
        {state.balance != null && (
          <span className="ml-auto text-base font-extrabold tabular-nums text-[#28a909]">
            {Number(state.balance).toFixed(2)} <span className="text-xs font-bold text-white/60">USD</span>
          </span>
        )}
        <button onClick={() => setRulesOpen((v) => !v)} aria-label="How to play"
          className={`${state.balance == null ? 'ml-auto' : ''} flex items-center gap-1.5 rounded-full bg-[#141516] px-3 py-1.5 text-xs font-bold text-white/80 hover:text-white`}>
          <BsInfoCircle size={13} /> <span className="hidden sm:inline">How to play</span>
        </button>
        <SoundToggles />
        {chat.enabled && (
          <button onClick={() => setChatOpen((v) => !v)} aria-label="Chat"
            className="relative flex h-8 w-8 items-center justify-center rounded-full bg-[#141516] text-white/85 hover:text-white xl:hidden">
            <BsChatDotsFill size={14} />
            {unread && <span className="absolute right-0.5 top-0.5 h-2 w-2 rounded-full bg-[#e50539]" />}
          </button>
        )}
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
          {s.bots_enabled && (
            <p className="mt-2 text-white/60">
              The live bets list and the chat include simulated players. They don’t stake real money and can’t affect a
              round — the crash point is fixed before betting opens.
            </p>
          )}
          <p className="mt-2 text-white/60">
            Rain: free bets are dropped on players who are playing or chatting. A free bet pays your stake × the multiplier
            minus the free stake, credited as a bonus; unused free bets expire after 24 hours.
          </p>
        </div>
      )}

      {!s.enabled && (
        <p className="mb-3 rounded-xl bg-[#f59e0b]/15 px-4 py-2.5 text-sm font-semibold text-[#fbbf24]">{s.display_name} is paused for a moment — bets will open again shortly.</p>
      )}
      {!user && (
        <p className="mb-3 rounded-xl bg-white/5 px-4 py-2.5 text-sm text-white/70">
          You’re watching. <a href="/login" target="_top" className="font-bold text-[#28a909] underline-offset-2 hover:underline">Log in</a> to place bets.
        </p>
      )}

      <div className={`grid grid-cols-1 gap-3 lg:grid-cols-[300px_minmax(0,1fr)] ${chat.enabled ? 'xl:grid-cols-[300px_minmax(0,1fr)_300px]' : ''}`}>
        {/* The lists take the height of the game column and scroll inside themselves. */}
        <div className="relative order-2 h-[420px] lg:order-1 lg:h-auto">
          <div className="h-full lg:absolute lg:inset-0">
            <BetsList bets={state.bets} loggedIn={!!user} />
          </div>
        </div>
        <div className="order-1 min-w-0 space-y-3 lg:order-2">
          <HistoryStrip history={state.history} settings={s} />
          <div className="relative">
            <FlightScene round={round} rate={rate} bettingSeconds={s.betting_seconds} now={now} name={s.display_name} />
            <CashoutToast toast={toast} />
          </div>
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
            {[1, 2].map((slot) => (
              <BetPanel
                key={slot} slot={slot} settings={s} round={round} bet={myBet(slot)} multiplier={multiplier}
                loggedIn={!!user}
                freeBet={(state.free_bets ?? [])[slot - 1]}
                onPlace={async (stake, auto, freeId) => { const r = await placeBet(slot, stake, auto, freeId); if (!r.error) sound.playBet(); return r; }}
                onCancel={async (id) => { const r = await cancelBet(id); if (!r.error) sound.playBet(); return r; }}
                onCashOut={cashOut}
              />
            ))}
          </div>
        </div>
        {chat.enabled && (
          <div className="relative order-3 hidden xl:block">
            <div className="absolute inset-0">
              <ChatPanel messages={chat.messages} enabled={chat.enabled} loggedIn={!!user} onSend={chat.send} />
            </div>
          </div>
        )}
      </div>

      {/* Smaller screens: chat slides in from the right. */}
      {chat.enabled && chatOpen && (
        <div className="fixed inset-0 z-[70] flex justify-end bg-black/50 xl:hidden" onClick={() => setChatOpen(false)}>
          <div className="h-full w-[340px] max-w-full p-2" onClick={(e) => e.stopPropagation()}>
            <ChatPanel messages={chat.messages} enabled={chat.enabled} loggedIn={!!user} onSend={chat.send} onClose={() => setChatOpen(false)} />
          </div>
        </div>
      )}
    </div>
  );
}
