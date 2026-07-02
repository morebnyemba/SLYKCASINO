'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BsGrid1X2Fill, BsTicketPerforated } from 'react-icons/bs';
import { GiTrophy, GiRollingDices } from 'react-icons/gi';
import { FaUser } from 'react-icons/fa';
import type { IconType } from 'react-icons';
import { useAuth } from '@/lib/auth-context';

interface NavTab {
  href: string;
  label: string;
  icon: IconType;
  center?: boolean;
  requiresAuth?: boolean;
}

const TABS: NavTab[] = [
  { href: '/', label: 'Lobby', icon: BsGrid1X2Fill },
  { href: '/sportsbook', label: 'Sports', icon: GiTrophy },
  { href: '/casino', label: 'Casino', icon: GiRollingDices, center: true },
  { href: '/account/bets', label: 'My Bets', icon: BsTicketPerforated, requiresAuth: true },
  { href: '/account/profile', label: 'Account', icon: FaUser, requiresAuth: true },
];

/** Mobile-only tab bar matching the Casino Lobby Mobile design; desktop keeps the header nav. */
export function BottomNav() {
  const pathname = usePathname();
  const { user } = useAuth();

  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 flex border-t border-border bg-card/95 px-1.5 pb-5 pt-2 backdrop-blur-md lg:hidden">
      {TABS.map((tab) => {
        const href = tab.requiresAuth && !user ? '/login' : tab.href;
        const active = tab.href === '/' ? pathname === '/' : pathname.startsWith(tab.href);
        const Icon = tab.icon;
        return (
          <Link
            key={tab.href}
            href={href}
            className={`flex flex-1 flex-col items-center gap-1 py-1 text-[10px] font-bold ${
              active ? 'text-secondary' : 'text-muted-foreground'
            }`}
          >
            {tab.center ? (
              <span className="-mt-[22px] flex h-[46px] w-[46px] items-center justify-center rounded-full bg-gradient-to-br from-gold to-gold/70 text-gold-foreground shadow-[0_6px_16px_rgba(0,0,0,0.35)]">
                <Icon size={22} />
              </span>
            ) : (
              <Icon size={20} />
            )}
            <span>{tab.label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
