'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useState } from 'react';
import { BsGrid1X2Fill } from 'react-icons/bs';
import { GiTrophy, GiRollingDices } from 'react-icons/gi';
import { FaGift, FaRegCommentDots, FaUser, FaSignOutAlt, FaBars, FaTimes, FaWallet, FaBell } from 'react-icons/fa';
import type { IconType } from 'react-icons';
import { useAuth } from '@/lib/auth-context';
import { useApi } from '@/lib/use-api';

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
  { href: '/promotions', label: 'Promotions', icon: FaGift },
  { href: '/livechat', label: 'Live Chat', icon: FaRegCommentDots },
];

const authedLinks = [
  { href: '/account/wallet', label: 'Wallet' },
  { href: '/account/bets', label: 'My Bets' },
];

export function SiteHeader() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const [menuOpen, setMenuOpen] = useState(false);
  const { data: wallet } = useApi<Wallet>(user ? '/wallet/' : null);
  const { data: notifications } = useApi<Notification[]>(user ? '/notifications/' : null);
  const unreadCount = notifications?.filter((n) => !n.read).length ?? 0;

  async function handleLogout() {
    await logout();
    router.push('/login');
    setMenuOpen(false);
  }

  return (
    <header className="sticky top-0 z-50 border-b border-border bg-primary shadow-md">
      <div className="mx-auto flex max-w-6xl items-center gap-8 px-4 py-3 sm:px-6">
        <Link href="/" className="flex items-center gap-2 text-lg font-extrabold tracking-tight text-white">
          <span className="rounded-md bg-primary px-2 py-1 text-sm text-primary-foreground">SLYK</span>
          <span className="hidden text-white/90 md:inline">Casino &amp; Sportsbook</span>
        </Link>

        <nav className="hidden flex-1 items-center gap-1 text-sm lg:flex">
          {links.map((l) => {
            const Icon = l.icon;
            return (
              <Link
                key={l.href}
                href={l.href}
                className="group flex items-center gap-1.5 rounded-md px-3 py-2 font-medium text-white/70 transition-all duration-150 hover:-translate-y-0.5 hover:bg-white/10 hover:text-white"
              >
                <Icon size={16} className="transition-transform duration-150 group-hover:scale-110" />
                {l.label}
              </Link>
            );
          })}
          {user && authedLinks.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              className="rounded-md px-3 py-2 font-medium text-white/70 transition-all duration-150 hover:-translate-y-0.5 hover:bg-white/10 hover:text-white"
            >
              {l.label}
            </Link>
          ))}
        </nav>

        <div className="ml-auto hidden items-center gap-3 text-sm lg:flex">
          {user ? (
            <>
              <Link
                href="/account/wallet"
                className="flex items-center gap-1.5 rounded-md bg-white/10 px-3 py-1.5 font-mono font-semibold text-white transition-colors hover:bg-white/20"
              >
                <FaWallet size={13} className="text-secondary" />
                {wallet?.balance ?? '—'} <span className="text-white/60">{wallet?.currency ?? ''}</span>
              </Link>
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
                className="flex items-center gap-1.5 rounded-md px-2 py-1.5 font-semibold text-white transition-colors hover:bg-white/10"
              >
                <FaUser size={14} />
                {user.username}
              </Link>
              <button
                onClick={handleLogout}
                className="flex items-center gap-1 rounded-md px-2 py-1.5 text-xs text-white/60 transition-colors hover:bg-white/10 hover:text-white"
              >
                <FaSignOutAlt size={12} />
                Log out
              </button>
            </>
          ) : (
            <>
              <Link href="/login" className="font-medium text-white/75 transition-colors hover:text-white">Log in</Link>
              <Link
                href="/register"
                className="rounded-md bg-secondary px-4 py-2 text-xs font-bold uppercase tracking-wide text-white shadow transition-transform duration-150 hover:scale-105 hover:opacity-90"
              >
                Sign up
              </Link>
            </>
          )}
        </div>

        <button
          aria-label="Toggle menu"
          onClick={() => setMenuOpen((v) => !v)}
          className="ml-auto flex h-9 w-9 items-center justify-center rounded-md text-white/80 transition-colors hover:bg-white/10 hover:text-white lg:hidden"
        >
          {menuOpen ? <FaTimes size={18} /> : <FaBars size={18} />}
        </button>
      </div>

      <div className="hidden border-t border-white/10 bg-primary/95 lg:block">
        <div className="mx-auto flex max-w-6xl items-center gap-6 px-4 py-2 sm:px-6">
          {links.map((l) => {
            const Icon = l.icon;
            return (
              <Link
                key={l.href}
                href={l.href}
                className="group flex flex-col items-center gap-1 text-[11px] font-medium text-white/70 transition-colors hover:text-white"
              >
                <span className="flex h-9 w-9 items-center justify-center rounded-full border border-white/20 transition-colors group-hover:border-white/60 group-hover:bg-white/10">
                  <Icon size={16} />
                </span>
                {l.label}
              </Link>
            );
          })}
        </div>
      </div>

      {menuOpen && (
        <nav className="flex flex-col gap-1 border-t border-white/10 bg-primary px-4 py-3 text-sm lg:hidden">
          {links.map((l) => {
            const Icon = l.icon;
            return (
              <Link
                key={l.href}
                href={l.href}
                onClick={() => setMenuOpen(false)}
                className="flex items-center gap-2 rounded-md px-3 py-2.5 font-medium text-white/80 transition-colors hover:bg-white/10 hover:text-white"
              >
                <Icon size={16} />
                {l.label}
              </Link>
            );
          })}
          {user && authedLinks.map((l) => (
            <Link
              key={l.href}
              href={l.href}
              onClick={() => setMenuOpen(false)}
              className="rounded-md px-3 py-2.5 font-medium text-white/80 transition-colors hover:bg-white/10 hover:text-white"
            >
              {l.label}
            </Link>
          ))}
          <div className="mt-2 flex flex-col gap-2 border-t border-white/10 pt-3">
            {user ? (
              <>
                <Link
                  href="/account/wallet"
                  onClick={() => setMenuOpen(false)}
                  className="flex items-center gap-2 rounded-md bg-white/10 px-3 py-2 font-mono font-semibold text-white"
                >
                  <FaWallet size={13} className="text-secondary" />
                  {wallet?.balance ?? '—'} <span className="text-white/60">{wallet?.currency ?? ''}</span>
                </Link>
                <Link
                  href="/account/notifications"
                  onClick={() => setMenuOpen(false)}
                  className="flex items-center gap-2 rounded-md px-3 py-2 font-semibold text-white hover:bg-white/10"
                >
                  <FaBell size={14} />
                  Notifications
                  {unreadCount > 0 && (
                    <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-secondary px-1 text-[10px] font-bold text-white">
                      {unreadCount > 9 ? '9+' : unreadCount}
                    </span>
                  )}
                </Link>
                <Link
                  href="/account/profile"
                  onClick={() => setMenuOpen(false)}
                  className="flex items-center gap-2 rounded-md px-3 py-2 font-semibold text-white hover:bg-white/10"
                >
                  <FaUser size={14} />
                  {user.username}
                </Link>
                <button
                  onClick={handleLogout}
                  className="flex items-center gap-2 rounded-md px-3 py-2 text-left text-white/70 hover:bg-white/10 hover:text-white"
                >
                  <FaSignOutAlt size={14} />
                  Log out
                </button>
              </>
            ) : (
              <>
                <Link
                  href="/login"
                  onClick={() => setMenuOpen(false)}
                  className="rounded-md px-3 py-2 font-medium text-white/80 hover:bg-white/10 hover:text-white"
                >
                  Log in
                </Link>
                <Link
                  href="/register"
                  onClick={() => setMenuOpen(false)}
                  className="rounded-md bg-secondary px-3 py-2 text-center text-xs font-bold uppercase tracking-wide text-white shadow hover:opacity-90"
                >
                  Sign up
                </Link>
              </>
            )}
          </div>
        </nav>
      )}
    </header>
  );
}
