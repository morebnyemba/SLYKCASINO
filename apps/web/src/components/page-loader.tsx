'use client';

import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { useSiteIdentity } from '@/lib/identity-context';

/** A small loading circle from the moment a player opens another page until it
 *  has loaded, shown for at least the admin's "page loading circle" time
 *  (Branding; default 3 s). It never blocks taps, and it gives up after 15 s
 *  if a page never arrives. */
export function PageLoader() {
  const identity = useSiteIdentity();
  const minMs = Math.max(0, Math.min(5, Number(identity.page_loader_seconds ?? 3))) * 1000;
  const pathname = usePathname();
  const [visible, setVisible] = useState(false);
  const started = useRef(0);
  const target = useRef<string | null>(null);
  const hideTimer = useRef<number | undefined>(undefined);

  // A tap on a link to another page of the site starts the circle.
  useEffect(() => {
    function onClick(e: MouseEvent) {
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
      const a = (e.target as HTMLElement | null)?.closest?.('a');
      if (!a || a.target === '_blank' || a.hasAttribute('download')) return;
      const url = new URL(a.href, window.location.href);
      if (url.origin !== window.location.origin || url.pathname === window.location.pathname) return;
      started.current = Date.now();
      target.current = url.pathname;
      window.clearTimeout(hideTimer.current);
      setVisible(true);
      hideTimer.current = window.setTimeout(() => setVisible(false), Math.max(minMs, 15000));
    }
    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
  }, [minMs]);

  // The new page has rendered: keep the circle until the minimum time has passed.
  useEffect(() => {
    if (!target.current) return;
    target.current = null;
    window.clearTimeout(hideTimer.current);
    const left = Math.max(0, minMs - (Date.now() - started.current));
    hideTimer.current = window.setTimeout(() => setVisible(false), left);
  }, [pathname, minMs]);

  useEffect(() => () => window.clearTimeout(hideTimer.current), []);

  if (!visible) return null;
  return (
    <div className="pointer-events-none fixed inset-0 z-[90] flex items-center justify-center" role="status" aria-live="polite">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-card/90 shadow-lg ring-1 ring-border backdrop-blur">
        <span className="h-7 w-7 animate-spin rounded-full border-[3px] border-secondary/25 border-t-secondary" />
      </span>
      <span className="sr-only">Loading…</span>
    </div>
  );
}
