'use client';

import { useEffect, useState } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { useSiteIdentity } from '@/lib/identity-context';
import { BRAND_MARK, BRAND_WORDMARK } from '@/components/logo';

/**
 * The one loader used across the site: the "B" mark breathing inside a spinning
 * green ring (the logo's colours), with the wordmark underneath. Used for the
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
        <div className="absolute inset-3 rounded-full bg-[radial-gradient(circle,rgba(47,209,47,0.35),transparent_70%)] blur-md" aria-hidden />
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
        // eslint-disable-next-line @next/next/no-img-element
        <img src={BRAND_WORDMARK.src} alt={identity.site_name} width={BRAND_WORDMARK.width} height={BRAND_WORDMARK.height} className="h-8 w-auto" />
      )}
      <p className="text-xs font-medium text-muted-foreground">{caption ?? 'Loading…'}</p>
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
