'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { GiJetFighter, GiSoccerBall, GiBasketballBall, GiTennisRacket } from 'react-icons/gi';
import { FaGift } from 'react-icons/fa';
import type { IconType } from 'react-icons';

const ITEMS: { href: string; label: string; icon?: IconType; live?: boolean }[] = [
  { href: '/sportsbook?tab=live', label: 'Live', live: true },
  { href: '/jet', label: 'Jet', icon: GiJetFighter },
  { href: '/sportsbook?sport=football', label: 'Football', icon: GiSoccerBall },
  { href: '/sportsbook?sport=basketball', label: 'Basketball', icon: GiBasketballBall },
  { href: '/sportsbook?sport=tennis', label: 'Tennis', icon: GiTennisRacket },
  { href: '/promotions', label: 'Promos', icon: FaGift },
];

/**
 * Mobile-only strip of one-tap shortcuts under the header (the "quick links" row
 * mobile sportsbooks use). Scrolls away with the page so it never eats screen space.
 */
export function MobileQuickNav() {
  const pathname = usePathname();
  // Account pages have their own tab strip; auth pages stay focused on the form.
  if (pathname.startsWith('/account') || ['/login', '/register', '/forgot-password', '/reset-password'].includes(pathname)) {
    return null;
  }

  return (
    <nav aria-label="Quick links" className="border-b border-border/60 bg-sidebar/60 lg:hidden">
      <div className="no-scrollbar flex gap-1.5 overflow-x-auto px-3 py-2">
        {ITEMS.map((item) => {
          const Icon = item.icon;
          const active = !item.href.includes('?') && pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-bold transition-colors ${
                active
                  ? 'border-secondary bg-secondary text-white'
                  : item.live
                    ? 'border-live/40 bg-live/10 text-foreground'
                    : 'border-border bg-card text-muted-foreground active:bg-muted'
              }`}
            >
              {item.live && <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-live" />}
              {Icon && <Icon size={13} className={active ? '' : 'text-secondary'} />}
              {item.label}
            </Link>
          );
        })}
      </div>
    </nav>
  );
}
