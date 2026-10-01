'use client';

import { useEffect, useState } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { useSiteIdentity } from '@/lib/identity-context';
import { BoltIcon } from '@/components/logo';

/**
 * The one loader used across the site: the brand mark inside a spinning ring,
 * with the site name. Used for the first-load splash, page changes, and route
 * loading screens so every wait looks the same.
 */
export function SiteLoader({ caption }: { caption?: string }) {
  const identity = useSiteIdentity();
  return (
    <div role="status" aria-live="polite" className="flex flex-col items-center gap-4">
      <div className="relative flex h-20 w-20 items-center justify-center">
        <svg viewBox="0 0 80 80" className="absolute inset-0 animate-spin [animation-duration:1.1s]" aria-hidden>
          <circle cx="40" cy="40" r="36" fill="none" stroke="currentColor" strokeWidth="4" className="text-muted" />
          <path d="M76 40A36 36 0 0 0 40 4" fill="none" strokeWidth="4" strokeLinecap="round" className="stroke-secondary" />
        </svg>
        {identity.logo_url ? (
          // eslint-disable-next-line @next/next/no-img-element
          <img src={identity.logo_url} alt="" className="h-10 w-10 rounded-xl object-contain" />
        ) : (
          <span className="flex h-12 w-12 animate-pulse items-center justify-center rounded-2xl bg-gradient-to-br from-secondary to-primary shadow-[0_6px_20px_color-mix(in_srgb,var(--secondary)_45%,transparent)] [animation-duration:1.6s]">
            <BoltIcon size={26} className="text-gold" />
          </span>
        )}
      </div>
      <p className="text-sm font-black tracking-tight">{identity.site_name}</p>
      <p className="-mt-3 text-xs font-medium text-muted-foreground">{caption ?? 'Loading…'}</p>
    </div>
  );
}

/** Route loading screen: the site loader centred in the content area. */
export function PageLoader({ caption }: { caption?: string }) {
  return (
    <div className="flex min-h-[60vh] items-center justify-center">
      <SiteLoader caption={caption} />
    </div>
  );
}

/**
 * First-load splash. Rendered on the server so it covers the page from the very
 * first paint, then fades out once the app is interactive. A CSS fallback
 * (.site-splash) also fades it after a few seconds if scripts never run.
 */
export function SiteSplash() {
  const [phase, setPhase] = useState<'shown' | 'leaving' | 'gone'>('shown');
  useEffect(() => {
    const leave = setTimeout(() => setPhase('leaving'), 150);
    const gone = setTimeout(() => setPhase('gone'), 550);
    return () => { clearTimeout(leave); clearTimeout(gone); };
  }, []);
  if (phase === 'gone') return null;
  return (
    <div
      aria-hidden={phase === 'leaving'}
      className={`site-splash fixed inset-0 z-[200] flex items-center justify-center bg-background transition-opacity duration-400 ${
        phase === 'leaving' ? 'pointer-events-none opacity-0' : 'opacity-100'
      }`}
    >
      <SiteLoader />
    </div>
  );
}

/**
 * Page-change loader: covers the page from a link click until the new page is
 * on screen. Waits 150ms before showing so fast navigations don't flicker.
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
    const show = setTimeout(() => setVisible(true), 150);
    // Never cover the page forever (e.g. a navigation the router cancelled).
    const giveUp = setTimeout(() => setPending(false), 15000);
    return () => { clearTimeout(show); clearTimeout(giveUp); };
  }, [pending]);

  // The URL changed: the new page (or its loading screen) is rendering.
  useEffect(() => { setPending(false); }, [pathname, search]);

  if (!visible) return null;
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-background/70 backdrop-blur-[3px]">
      <SiteLoader />
    </div>
  );
}
