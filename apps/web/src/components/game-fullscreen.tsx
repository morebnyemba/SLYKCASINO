'use client';

import { useEffect } from 'react';
import { usePathname } from 'next/navigation';

/** Pages that open in full screen (the browser only allows it during a tap, so
 * it's requested from the tap on the link, before the page changes). */
const FULLSCREEN_PATHS = ['/aviator'];

export function wantsFullscreen(pathname: string) {
  return FULLSCREEN_PATHS.some((p) => pathname === p || pathname.startsWith(`${p}/`));
}

/** Best effort: Android Chrome and desktop browsers go full screen; iPhone Safari
 * has no web full screen, where the game still fills the whole window. */
export function enterFullscreen() {
  const el = document.documentElement as HTMLElement & { webkitRequestFullscreen?: () => void };
  if (document.fullscreenElement) return;
  try {
    if (el.requestFullscreen) void el.requestFullscreen({ navigationUI: 'hide' }).catch(() => {});
    else el.webkitRequestFullscreen?.();
  } catch { /* not allowed here */ }
}

export function exitFullscreen() {
  if (document.fullscreenElement) void document.exitFullscreen().catch(() => {});
}

/**
 * Mounted once in the app shell: a tap on any link to Aviator (sidebar, quick
 * chips, home card, search) switches the page to full screen as it opens, and
 * leaving for any other page leaves full screen.
 */
export function GameFullscreenLauncher() {
  const pathname = usePathname();
  useEffect(() => {
    if (!wantsFullscreen(pathname)) exitFullscreen();
  }, [pathname]);

  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as Element | null)?.closest?.('a');
      if (!a || a.target === '_blank') return;
      let url: URL;
      try { url = new URL(a.href, window.location.href); } catch { return; }
      if (url.origin === window.location.origin && wantsFullscreen(url.pathname)) enterFullscreen();
    }
    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
  }, []);
  return null;
}
