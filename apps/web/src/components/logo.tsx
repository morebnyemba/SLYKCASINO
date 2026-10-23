'use client';

import Link from 'next/link';
import { useSiteIdentity } from '@/lib/identity-context';

// Brand artwork (public/brand): the BetBlits badge wordmark (4:1, its glow fades to
// transparent) and the square bolt-and-B mark. An operator-uploaded logo (Branding) overrides them.
export const BRAND_WORDMARK = { src: '/brand/wordmark.webp', width: 961, height: 240 };
export const BRAND_MARK = { src: '/brand/mark.webp', width: 512, height: 512 };

/** The site logo, linking home. `markOnly` shows just the square mark (collapsed rail). */
export function Logo({ markOnly = false, className = '', imgClassName = 'h-11' }: {
  markOnly?: boolean;
  className?: string;
  /** Height classes for the wordmark (it keeps its 4:1 shape). */
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
        // eslint-disable-next-line @next/next/no-img-element
        <img
          src={BRAND_WORDMARK.src} width={BRAND_WORDMARK.width} height={BRAND_WORDMARK.height} alt={identity.site_name}
          className={`w-auto object-contain drop-shadow-[0_2px_8px_rgba(40,140,255,0.25)] transition-transform duration-300 group-hover:scale-[1.03] ${imgClassName}`}
        />
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
      className={`h-9 w-9 shrink-0 object-contain drop-shadow-[0_2px_6px_rgba(40,140,255,0.3)] ${className}`}
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
