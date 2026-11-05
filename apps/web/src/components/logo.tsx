'use client';

import Link from 'next/link';
import { useSiteIdentity } from '@/lib/identity-context';

// Brand artwork (public/brand): the BetBlits wordmark (~3.45:1, transparent) in
// two versions — navy "Bet" for light backgrounds, white "Bet" for dark ones —
// and the square bolt-tile mark. An operator-uploaded logo (Branding) overrides them.
export const BRAND_WORDMARK = { src: '/brand/wordmark.webp', width: 1036, height: 300 };
export const BRAND_WORDMARK_DARK = { src: '/brand/wordmark-dark.webp', width: 1036, height: 300 };
export const BRAND_MARK = { src: '/brand/mark.webp', width: 512, height: 512 };
// Text-only wordmark (~4.4:1) shown under the loader, same two versions.
export const LOADER_WORDMARK = { src: '/brand/loader-wordmark.webp', width: 700, height: 160 };
export const LOADER_WORDMARK_DARK = { src: '/brand/loader-wordmark-dark.webp', width: 700, height: 160 };

/** The wordmark for the current theme. `on="dark"` forces the white-text
 *  version (for always-dark surfaces such as gradient panels). */
export function Wordmark({ alt, className = '', on, art }: {
  alt: string; className?: string; on?: 'dark';
  /** Use the text-only loader artwork instead of the icon + text wordmark. */
  art?: 'loader';
}) {
  const [BRAND_WORDMARK_LIGHT, BRAND_WORDMARK_ON_DARK] = art === 'loader'
    ? [LOADER_WORDMARK, LOADER_WORDMARK_DARK] : [BRAND_WORDMARK, BRAND_WORDMARK_DARK];
  const img = (w: typeof BRAND_WORDMARK, extra: string) => (
    // eslint-disable-next-line @next/next/no-img-element
    <img src={w.src} width={w.width} height={w.height} alt={alt} className={`w-auto object-contain ${extra} ${className}`} />
  );
  if (on === 'dark') return img(BRAND_WORDMARK_ON_DARK, '');
  return <>{img(BRAND_WORDMARK_LIGHT, 'brand-on-light')}{img(BRAND_WORDMARK_ON_DARK, 'brand-on-dark')}</>;
}

/** The site logo, linking home. `markOnly` shows just the square mark (collapsed rail). */
export function Logo({ markOnly = false, className = '', imgClassName = 'h-11' }: {
  markOnly?: boolean;
  className?: string;
  /** Height classes for the wordmark (it keeps its ~3.5:1 shape). */
  imgClassName?: string;
}) {
  const identity = useSiteIdentity();
  return (
    <Link href="/" aria-label={`${identity.site_name} home`} className={`group flex shrink-0 items-center ${className}`}>
      {markOnly ? (
        <LogoMark className="transition-transform duration-300 group-hover:-rotate-6" />
      ) : identity.logo_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={identity.logo_url} alt={identity.site_name} className="h-8 w-auto max-w-[160px] object-contain" />
      ) : (
        <Wordmark alt={identity.site_name}
          className={`drop-shadow-[0_2px_8px_rgba(70,40,255,0.22)] transition-transform duration-300 group-hover:scale-[1.03] ${imgClassName}`} />
      )}
    </Link>
  );
}

/** The square brand mark on its own (no link), e.g. inside the collapsed rail's expand button. */
export function LogoMark({ className = '' }: { className?: string }) {
  const identity = useSiteIdentity();
  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={identity.logo_url || BRAND_MARK.src} width={BRAND_MARK.width} height={BRAND_MARK.height} alt=""
      className={`h-9 w-9 shrink-0 object-contain drop-shadow-[0_2px_6px_rgba(90,50,255,0.35)] ${className}`}
    />
  );
}

/** The BetBlits lightning bolt (same shape as the app icons in /public/icons). */
export function BoltIcon({ size = 16, className = '' }: { size?: number; className?: string }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} aria-hidden className={className} fill="currentColor">
      <path d="M13.6 1.8 4.4 13.4h6.1l-1.3 8.8 10.4-12.6h-6.3l.3-7.8z" />
    </svg>
  );
}
