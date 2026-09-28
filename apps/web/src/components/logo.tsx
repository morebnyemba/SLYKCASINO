'use client';

import Link from 'next/link';
import { GiPerspectiveDiceSixFacesRandom } from 'react-icons/gi';
import { useSiteIdentity } from '@/lib/identity-context';

/** Brand mark + name. `markOnly` shows just the square mark (collapsed rail, tight mobile header). */
export function Logo({ markOnly = false, className = '', nameClassName = '' }: {
  markOnly?: boolean;
  className?: string;
  /** Extra classes for the wordmark, e.g. to hide it on very narrow screens. */
  nameClassName?: string;
}) {
  const identity = useSiteIdentity();
  return (
    <Link href="/" aria-label={`${identity.site_name} home`} className={`group flex shrink-0 items-center gap-2 ${className}`}>
      {identity.logo_url && !markOnly ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={identity.logo_url} alt={identity.site_name} className="h-8 w-auto max-w-[140px] object-contain" />
      ) : (
        <>
          <LogoMark className="transition-transform duration-300 group-hover:-rotate-12" />
          {!markOnly && <span className={`text-[17px] font-black tracking-tight ${nameClassName}`}>{identity.site_name}</span>}
        </>
      )}
    </Link>
  );
}

/** The square brand mark on its own (no link), e.g. inside the collapsed rail's expand button. */
export function LogoMark({ className = '' }: { className?: string }) {
  return (
    <span className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-secondary to-primary text-white shadow-[0_4px_14px_color-mix(in_srgb,var(--secondary)_40%,transparent)] ring-1 ring-white/10 ${className}`}>
      <GiPerspectiveDiceSixFacesRandom size={19} />
    </span>
  );
}
