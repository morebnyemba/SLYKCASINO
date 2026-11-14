'use client';

import { useEffect, useState } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { useSiteIdentity } from '@/lib/identity-context';
import { BRAND_MARK, Wordmark } from '@/components/logo';

/**
 * The one loader used across the site: the bolt-tile mark breathing inside a
 * spinning cyan → blue → violet → magenta ring (the logo's ring), with the
 * text wordmark underneath. Used for the
 * first-load splash, page changes and route loading screens so every wait looks
 * the same. An operator-uploaded logo replaces the artwork.
 */
export function SiteLoader({ caption }: { caption?: string }) {
  const identity = useSiteIdentity();
  const custom = identity.logo_url;
  return (
    <div role="status" aria-live="polite" className="flex flex-col items-center gap-3">
      <div className="relative h-24 w-24">
        {/* Soft glow behind the mark */}
        <div className="absolute inset-3 rounded-full bg-[radial-gradient(circle,rgba(110,60,255,0.4),transparent_70%)] blur-md" aria-hidden />
        {/* Track + spinning comet ring */}
        <div className="absolute inset-0 rounded-full border-[3px] border-muted" aria-hidden />
        <div className="brand-ring absolute inset-0 animate-spin rounded-full [animation-duration:1.1s]" aria-hidden />
        {/* eslint-disable-next-line @next/next/no-img-element */}
        <img
          src={custom || BRAND_MARK.src} alt="" width={BRAND_MARK.width} height={BRAND_MARK.height}
          className="brand-breathe absolute inset-0 m-auto h-14 w-14 object-contain"
        />
      </div>
      {custom ? (
        <p className="text-sm font-black tracking-tight">{identity.site_name}</p>
      ) : (
        <Wordmark art="loader" alt={identity.site_name} className="h-7" />
      )}
      <p className="text-xs font-medium text-muted-foreground">{caption ?? 'Loading…'}</p>
    </div>
  );
}

/** In-page wait (account pages, game launch): a small spinner, not the branded splash. */
export function PageLoader({ caption }: { caption?: string }) {
  return (
    <div role="status" aria-live="polite" className="flex min-h-[40vh] flex-col items-center justify-center gap-2.5">
      <span className="h-7 w-7 animate-spin rounded-full border-[3px] border-muted border-t-secondary" aria-hidden />
      <span className="text-xs font-medium text-muted-foreground">{caption ?? 'Loading…'}</span>
    </div>
  );
}

/**
 * First-open splash: once per browser session, and brief. Rendered on the
 * server so it covers the first paint, then faded out by CSS after ~0.6s —
 * it never waits for the app's JavaScript (on a slow phone that took seconds
 * while the page underneath was already there). The head script in the root
 * layout marks repeat loads in the same session (`data-splash="off"`), which
 * hides it from the start. Purely decorative: it never blocks taps.
 */
export function SiteSplash() {
  return (
    <div aria-hidden className="site-splash pointer-events-none fixed inset-0 z-[200] flex items-center justify-center bg-background">
      <SiteLoader />
    </div>
  );
}

/**
 * Page-change feedback: a thin bar across the top from a link click until the
 * new page is on screen. The current page stays visible and usable underneath.
 * Waits 120ms before showing so instant navigations show nothing at all.
 */
export function NavigationLoader() {
  const pathname = usePathname();
  const search = useSearchParams();
  const [pending, setPending] = useState(false);
  const [visible, setVisible] = useState(false);

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
      setPending(true);
    }
    document.addEventListener('click', onClick, true);
    return () => document.removeEventListener('click', onClick, true);
  }, []);

  useEffect(() => {
    if (!pending) { setVisible(false); return; }
    const show = setTimeout(() => setVisible(true), 120);
    // Never hang around (e.g. a navigation the router cancelled).
    const giveUp = setTimeout(() => setPending(false), 15000);
    return () => { clearTimeout(show); clearTimeout(giveUp); };
  }, [pending]);

  // The URL changed: the new page (or its skeleton) is rendering.
  useEffect(() => { setPending(false); }, [pathname, search]);

  if (!visible) return null;
  return (
    <div role="progressbar" aria-label="Loading page" className="pointer-events-none fixed inset-x-0 top-0 z-[90] h-[3px] overflow-hidden">
      <div className="nav-progress h-full bg-secondary shadow-[0_0_8px_var(--secondary)]" />
    </div>
  );
}
