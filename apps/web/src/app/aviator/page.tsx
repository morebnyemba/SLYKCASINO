'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { BsArrowsFullscreen, BsChevronLeft, BsFullscreenExit } from 'react-icons/bs';
import { WALLET_CHANGED } from '@/components/cashout';
import { useApi } from '@/lib/use-api';

const GAME_PATH = '/play/aviator';

/**
 * Aviator opens like a casino game: the game runs in its own frame
 * (/play/aviator, no site navigation) under a slim bar with the way back and a
 * full-screen button.
 */
export default function AviatorLauncher() {
  const { data } = useApi<{ settings?: { display_name?: string } }>('/jet/state/', { public: true });
  const name = data?.settings?.display_name ?? 'BetBlits Aviator';
  const boxRef = useRef<HTMLDivElement>(null);
  const [full, setFull] = useState(false);

  // The game posts here when a bet or cash-out moves the balance; the header listens for WALLET_CHANGED.
  useEffect(() => {
    const onMessage = (e: MessageEvent) => {
      if (e.origin === window.location.origin && e.data?.type === 'slyk:wallet-changed') {
        window.dispatchEvent(new Event(WALLET_CHANGED));
      }
    };
    const onFull = () => setFull(document.fullscreenElement === boxRef.current);
    window.addEventListener('message', onMessage);
    document.addEventListener('fullscreenchange', onFull);
    return () => {
      window.removeEventListener('message', onMessage);
      document.removeEventListener('fullscreenchange', onFull);
    };
  }, []);

  async function toggleFull() {
    if (document.fullscreenElement) { await document.exitFullscreen().catch(() => {}); return; }
    const box = boxRef.current;
    if (box?.requestFullscreen) {
      try { await box.requestFullscreen(); return; } catch { /* fall through */ }
    }
    // No element full-screen (e.g. iPhone Safari): open the game on its own page.
    window.location.href = GAME_PATH;
  }

  return (
    <div className="-mx-3 -my-4 sm:mx-0 sm:my-0">
      <div className="flex items-center gap-2 border-b border-[#2c2d30] bg-[#1b1c1d] px-3 py-2 text-white sm:rounded-t-2xl">
        <Link href="/sportsbook" className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-bold text-white/70 hover:bg-white/10 hover:text-white">
          <BsChevronLeft size={11} /> Back
        </Link>
        <h1 className="flex-1 truncate text-center text-sm font-extrabold">{name}</h1>
        <button onClick={toggleFull} aria-label={full ? 'Exit full screen' : 'Full screen'}
          className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-bold text-white/70 hover:bg-white/10 hover:text-white">
          {full ? <BsFullscreenExit size={13} /> : <BsArrowsFullscreen size={12} />}
          <span className="hidden sm:inline">{full ? 'Exit' : 'Full screen'}</span>
        </button>
      </div>
      <div ref={boxRef} className="overflow-hidden bg-[#0e0e0e] sm:rounded-b-2xl">
        <iframe
          src={GAME_PATH}
          title={name}
          allow="fullscreen; autoplay"
          className={`block w-full border-0 ${full ? 'h-screen' : 'h-[calc(100dvh-196px)] min-h-[600px] lg:h-[calc(100dvh-150px)] lg:min-h-[640px]'}`}
        />
      </div>
    </div>
  );
}
