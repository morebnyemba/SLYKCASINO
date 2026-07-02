'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { BsGrid1X2Fill } from 'react-icons/bs';
import { GiTrophy, GiRollingDices, GiPodiumWinner, GiPerspectiveDiceSixFacesRandom } from 'react-icons/gi';
import { FaGift, FaRegCommentDots, FaUser, FaSignOutAlt, FaWallet, FaBell } from 'react-icons/fa';
import type { IconType } from 'react-icons';
import { useAuth } from '@/lib/auth-context';
import { useApi } from '@/lib/use-api';
import { ThemeToggle, SettingsMenu } from '@/components/settings-menu';
import { DepositModal } from '@/components/deposit-modal';
import { useSiteIdentity } from '@/lib/identity-context';

interface Wallet {
  balance?: string;
  currency?: string;
}

interface Notification {
  id: number;
  read: boolean;
}

const links: { href: string; label: string; icon: IconType }[] = [
  { href: '/', label: 'Lobby', icon: BsGrid1X2Fill },
  { href: '/sportsbook', label: 'Sportsbook', icon: GiTrophy },
  { href: '/casino', label: 'Casino', icon: GiRollingDices },
  { href: '/tournaments', label: 'Tournaments', icon: GiPodiumWinner },
  { href: '/promotions', label: 'Promotions', icon: FaGift },
  { href: '/livechat', label: 'Live Chat', icon: FaRegCommentDots },
];

export function SiteHeader() {
  const { user, logout } = useAuth();
  const identity = useSiteIdentity();
  const router = useRouter();
  const [depositOpen, setDepositOpen] = useState(false);
  const { data: wallet } = useApi<Wallet>(user ? '/wallet/' : null);
  const { data: notifications } = useApi<Notification[]>(user ? '/notifications/' : null);
  const unreadCount = notifications?.filter((n) => !n.read).length ?? 0;

  async function handleLogout() {
    await logout();
    router.push('/login');
  }

  return (
    <>
    <header className="sticky top-0 z-50 border-b border-gold/30 bg-gradient-to-r from-primary via-primary to-primary/80 shadow-lg shadow-black/20">
      <div className="flex items-center gap-4 px-4 py-3 sm:px-6">
        <Link href="/" className="group flex items-center gap-2.5">
          {identity.logo_url ? (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={identity.logo_url} alt={identity.site_name} className="h-9 w-auto max-w-[160px] object-contain" />
          ) : (
            <span className="flex items-center gap-1 rounded-md bg-gradient-to-br from-gold to-gold/70 px-2.5 py-1 text-sm font-black tracking-wide text-white shadow-inner shadow-black/30 ring-1 ring-white/15 transition-transform duration-300 group-hover:-rotate-6 group-hover:scale-110">
              <GiPerspectiveDiceSixFacesRandom size={14} className="text-white/90" />
            </span>
          )}
          <span className="hidden flex-col leading-none md:flex">
            <span className="text-lg font-extrabold tracking-tight text-white">{identity.site_name}</span>
            <span className="relative mt-0.5 h-3.5 w-36 overflow-hidden text-[11px] font-medium">
              <span className="absolute inset-0 block text-white/60 transition-transform duration-300 ease-out group-hover:-translate-y-full">
                Sportsbook &amp; Casino
              </span>
              <span className="absolute inset-0 block translate-y-full text-gold transition-transform duration-300 ease-out group-hover:translate-y-0">
                {identity.tagline}
              </span>
            </span>
          </span>
        </Link>

        <nav className="hidden flex-1 items-center gap-1 text-sm min-[1320px]:flex">
          {links.map((l) => {
            const Icon = l.icon;
            return (
              <Link
                key={l.href}
                href={l.href}
                className="group flex items-center gap-1 rounded-md px-2 py-2 font-medium text-white/70 transition-all duration-150 hover:-translate-y-0.5 hover:bg-white/10 hover:text-white"
              >
                <Icon size={16} className="transition-transform duration-150 group-hover:scale-110" />
                {l.label}
              </Link>
            );
          })}
        </nav>

        <div className="ml-auto hidden items-center gap-1 text-sm min-[1320px]:flex">
          <ThemeToggle />
          <SettingsMenu />
          <div className="mx-1 h-5 w-px bg-white/15" />
          {user ? (
            <div className="flex items-center gap-3">
              <Link
                href="/account/wallet"
                className="flex items-center gap-1.5 rounded-md bg-white/10 px-3 py-1.5 font-mono font-semibold text-white transition-colors hover:bg-white/20"
              >
                <FaWallet size={13} className="text-secondary" />
                {wallet?.balance ?? '—'} <span className="hidden text-white/60 2xl:inline">{wallet?.currency ?? ''}</span>
              </Link>
              <button
                onClick={() => setDepositOpen(true)}
                aria-label="Deposit"
                title="Deposit"
                className="rounded-md bg-gradient-to-br from-gold to-gold/70 px-2.5 py-1.5 text-xs font-extrabold text-gold-foreground shadow transition-transform hover:scale-105 2xl:px-3"
              >
                <span className="2xl:hidden">+</span>
                <span className="hidden 2xl:inline">Deposit</span>
              </button>
              <Link
                href="/account/notifications"
                aria-label="Notifications"
                className="relative flex h-9 w-9 items-center justify-center rounded-md text-white/80 transition-colors hover:bg-white/10 hover:text-white"
              >
                <FaBell size={15} />
                {unreadCount > 0 && (
                  <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-secondary px-1 text-[10px] font-bold text-white">
                    {unreadCount > 9 ? '9+' : unreadCount}
                  </span>
                )}
              </Link>
              <Link
                href="/account/profile"
                aria-label={user.username}
                title={user.username}
                className="flex items-center gap-1.5 rounded-md px-2 py-1.5 font-semibold text-white transition-colors hover:bg-white/10"
              >
                <FaUser size={14} />
                <span className="hidden 2xl:inline">{user.username}</span>
              </Link>
              <button
                onClick={handleLogout}
                aria-label="Log out"
                title="Log out"
                className="flex items-center gap-1 rounded-md px-2 py-1.5 text-xs text-white/60 transition-colors hover:bg-white/10 hover:text-white"
              >
                <FaSignOutAlt size={12} />
                <span className="hidden 2xl:inline">Log out</span>
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-3">
              <Link href="/login" className="font-medium text-white/75 transition-colors hover:text-white">Log in</Link>
              <Link
                href="/register"
                className="rounded-md bg-secondary px-4 py-2 text-xs font-bold uppercase tracking-wide text-white shadow transition-transform duration-150 hover:scale-105 hover:opacity-90"
              >
                Sign up
              </Link>
            </div>
          )}
        </div>

        <div className="ml-auto flex items-center gap-2 min-[1320px]:hidden">
          {user ? (
            <>
              <Link
                href="/account/wallet"
                className="flex items-center gap-1.5 rounded-md bg-white/10 px-2.5 py-1.5 text-xs font-mono font-semibold text-white transition-colors hover:bg-white/20"
              >
                <FaWallet size={11} className="text-secondary" />
                {wallet?.balance ?? '—'}
              </Link>
              <button
                onClick={() => setDepositOpen(true)}
                aria-label="Deposit"
                className="rounded-md bg-gradient-to-br from-gold to-gold/70 px-2.5 py-1.5 text-xs font-extrabold text-gold-foreground shadow transition-transform hover:scale-105"
              >
                Deposit
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className="text-xs font-medium text-white/75 transition-colors hover:text-white">Log in</Link>
              <Link
                href="/register"
                className="rounded-md bg-secondary px-2.5 py-1.5 text-xs font-bold uppercase tracking-wide text-white shadow transition-transform hover:scale-105 hover:opacity-90"
              >
                Sign up
              </Link>
            </>
          )}
        </div>
      </div>
    </header>
    <DepositModal open={depositOpen} onClose={() => setDepositOpen(false)} />
    </>
  );
}
