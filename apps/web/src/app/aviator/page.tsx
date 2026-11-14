'use client';

import { useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { BsArrowsFullscreen, BsChevronLeft, BsFullscreenExit } from 'react-icons/bs';
import { WALLET_CHANGED } from '@/components/cashout';
import { enterFullscreen, exitFullscreen } from '@/components/game-fullscreen';
import { useApi } from '@/lib/use-api';

const GAME_PATH = '/play/aviator';

/**
 * Aviator always opens full screen: the game (its own frame, /play/aviator) covers
 * the whole window above the site's header and tab bar, and the browser goes full
 * screen from the tap that opened it (GameFullscreenLauncher). A slim bar keeps the
 * way back. Leaving Aviator leaves full screen.
 */
export default function AviatorLauncher() {
  const router = useRouter();
  const { data } = useApi<{ settings?: { display_name?: string } }>('/jet/state/', { public: true });
  const name = data?.settings?.display_name ?? 'BetBlits Aviator';
  const [full, setFull] = useState(false);
  const [canFull, setCanFull] = useState(false);

  useEffect(() => {
    // The game posts here when a bet or cash-out moves the balance; the header listens for WALLET_CHANGED.
    const onMessage = (e: MessageEvent) => {
      if (e.origin === window.location.origin && e.data?.type === 'slyk:wallet-changed') {
        window.dispatchEvent(new Event(WALLET_CHANGED));
      }
    };
    const onFull = () => setFull(!!document.fullscreenElement);
    onFull();
    setCanFull(!!document.documentElement.requestFullscreen);
    window.addEventListener('message', onMessage);
    document.addEventListener('fullscreenchange', onFull);
    // The page behind doesn't scroll while the game covers it.
    const overflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    return () => {
      window.removeEventListener('message', onMessage);
      document.removeEventListener('fullscreenchange', onFull);
      document.body.style.overflow = overflow;
    };
  }, []);

  function back() {
    exitFullscreen();
    if (window.history.length > 1) router.back();
    else router.push('/sportsbook');
  }

  return (
    <div className="fixed inset-0 z-[70] flex flex-col bg-[#0e0e0e] pt-[env(safe-area-inset-top)]">
      <div className="flex shrink-0 items-center gap-2 border-b border-[#2c2d30] bg-[#1b1c1d] px-3 py-1.5 text-white">
        <button onClick={back} className="flex items-center gap-1 rounded-lg px-2 py-1 text-xs font-bold text-white/70 hover:bg-white/10 hover:text-white">
          <BsChevronLeft size={11} /> Back
        </button>
        <h1 className="flex-1 truncate text-center text-sm font-extrabold">{name}</h1>
        {canFull ? (
          <button onClick={() => (full ? exitFullscreen() : enterFullscreen())} aria-label={full ? 'Exit full screen' : 'Full screen'}
            className="flex items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-bold text-white/70 hover:bg-white/10 hover:text-white">
            {full ? <BsFullscreenExit size={13} /> : <BsArrowsFullscreen size={12} />}
            <span className="hidden sm:inline">{full ? 'Exit' : 'Full screen'}</span>
          </button>
        ) : <span className="w-14" aria-hidden />}
      </div>
      <iframe src={GAME_PATH} title={name} allow="fullscreen; autoplay" className="block min-h-0 w-full flex-1 border-0" />
    </div>
  );
}
