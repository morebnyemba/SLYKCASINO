'use client';

import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { realtimeConnected } from '@/lib/live-board';

/**
 * Re-renders the server page while the tab is visible, as a fallback for live
 * data: every `seconds` while the realtime socket is down, but only every
 * `connectedSeconds` while it's up (scores, prices and suspensions then arrive
 * over the socket, and a full server render would refetch the whole page).
 */
export function AutoRefresh({ seconds, connectedSeconds = 120 }: { seconds: number; connectedSeconds?: number }) {
  const router = useRouter();
  useEffect(() => {
    let last = Date.now();
    const id = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      const due = (realtimeConnected() ? connectedSeconds : seconds) * 1000;
      if (Date.now() - last < due) return;
      last = Date.now();
      router.refresh();
    }, 5_000);
    return () => window.clearInterval(id);
  }, [router, seconds, connectedSeconds]);
  return null;
}
