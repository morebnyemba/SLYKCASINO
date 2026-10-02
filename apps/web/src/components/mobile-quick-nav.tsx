'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BsHouseDoorFill } from 'react-icons/bs';
import { GiRocketFlight, GiSoccerBall, GiCherry, GiPokerHand, GiPodiumWinner, GiBasketballBall } from 'react-icons/gi';
import { FaGift } from 'react-icons/fa';
import type { IconType } from 'react-icons';

const ITEMS: { href: string; label: string; icon?: IconType; live?: boolean }[] = [
  { href: '/home', label: 'Home', icon: BsHouseDoorFill },
  { href: '/sportsbook?tab=live', label: 'Live', live: true },
  { href: '/casino/crash', label: 'Aviator', icon: GiRocketFlight },
  { href: '/sportsbook?sport=football', label: 'Football', icon: GiSoccerBall },
  { href: '/casino?category=slots', label: 'Slots', icon: GiCherry },
  { href: '/casino?category=live', label: 'Live casino', icon: GiPokerHand },
  { href: '/sportsbook?sport=basketball', label: 'Basketball', icon: GiBasketballBall },
  { href: '/promotions', label: 'Promos', icon: FaGift },
  { href: '/tournaments', label: 'Tournaments', icon: GiPodiumWinner },
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
