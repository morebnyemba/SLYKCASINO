'use client';

import { usePathname, useSearchParams } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';

/**
 * A thin progress bar across the top of the page from the moment an internal
 * link is clicked until the new page is on screen — immediate feedback even
 * when a page takes a while to load.
 */
export function NavProgress() {
  const pathname = usePathname();
  const search = useSearchParams();
  const [state, setState] = useState<'idle' | 'loading' | 'done'>('idle');
  const timers = useRef<ReturnType<typeof setTimeout>[]>([]);

  const clear = () => { timers.current.forEach(clearTimeout); timers.current = []; };

  // Start on any same-origin link click that changes the URL.
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as Element | null)?.closest?.('a');
      if (!a || a.target === '_blank' || a.hasAttribute('download')) return;
      const href = a.getAttribute('href');
      if (!href || href.startsWith('#') || href.startsWith('mailto:') || href.startsWith('tel:')) return;
      let url: URL;
      try { url = new URL(a.href, window.location.href); } catch { return; }
      if (url.origin !== window.location.origin) return;
      if (url.pathname === window.location.pathname && url.search === window.location.search) return;
      clear();
      setState('loading');
      // Never spin forever (e.g. a navigation the router cancelled).
      timers.current.push(setTimeout(() => setState('idle'), 15000));
    }
    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
  }, []);

  // The URL changed: the new page is rendering — finish and fade out.
  useEffect(() => {
    setState((s) => (s === 'loading' ? 'done' : s));
    clear();
    timers.current.push(setTimeout(() => setState('idle'), 400));
  }, [pathname, search]);

  useEffect(() => clear, []);

  if (state === 'idle') return null;
  return (
    <div aria-hidden className="pointer-events-none fixed inset-x-0 top-0 z-[100] h-[3px]">
      <div
        className={`h-full bg-secondary shadow-[0_0_10px_var(--secondary)] ${
          state === 'loading' ? 'animate-nav-progress' : 'w-full opacity-0 transition-opacity duration-300'
        }`}
      />
    </div>
  );
}
