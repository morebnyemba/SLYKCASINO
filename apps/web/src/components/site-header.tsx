'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useState } from 'react';
import { GiTrophy, GiRollingDices, GiPerspectiveDiceSixFacesRandom } from 'react-icons/gi';
import {
  FaGift, FaUser, FaSignOutAlt, FaWallet, FaBell, FaIdCard, FaShieldAlt, FaChevronDown, FaHistory,
} from 'react-icons/fa';
import { BsTicketPerforated } from 'react-icons/bs';
import type { IconType } from 'react-icons';
import { useAuth } from '@/lib/auth-context';
import { useApi } from '@/lib/use-api';
import { SettingsMenu } from '@/components/settings-menu';
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

const PRODUCT_TABS: { href: string; label: string; icon: IconType }[] = [
  { href: '/casino', label: 'Casino', icon: GiRollingDices },
  { href: '/sportsbook', label: 'Sports', icon: GiTrophy },
  { href: '/promotions', label: 'Promotions', icon: FaGift },
];

const ACCOUNT_LINKS: { href: string; label: string; icon: IconType }[] = [
  { href: '/account/profile', label: 'Profile', icon: FaUser },
  { href: '/account/wallet', label: 'Wallet', icon: FaWallet },
  { href: '/account/bets', label: 'My bets', icon: BsTicketPerforated },
  { href: '/account/casino', label: 'Casino history', icon: FaHistory },
  { href: '/account/verification', label: 'Verification', icon: FaIdCard },
  { href: '/account/settings', label: 'Responsible gaming', icon: FaShieldAlt },
];

function formatBalance(balance?: string): string {
  if (balance == null) return '—';
  const n = Number(balance);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : balance;
}

function Logo() {
  const identity = useSiteIdentity();
  return (
    <Link href="/" className="group flex shrink-0 items-center gap-2">
      {identity.logo_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={identity.logo_url} alt={identity.site_name} className="h-8 w-auto max-w-[140px] object-contain" />
      ) : (
        <>
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-gradient-to-br from-secondary to-primary text-white shadow-inner shadow-black/30 transition-transform duration-300 group-hover:-rotate-12">
            <GiPerspectiveDiceSixFacesRandom size={18} />
          </span>
          <span className="text-lg font-black tracking-tight">{identity.site_name}</span>
        </>
      )}
    </Link>
  );
}

function UserMenu({ username, unreadCount, onLogout }: { username: string; unreadCount: number; onLogout: () => void }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="relative">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Account menu"
        aria-expanded={open}
        className="flex h-10 items-center gap-2 rounded-lg px-1.5 transition-colors hover:bg-muted sm:px-2"
      >
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-secondary to-primary text-sm font-bold text-white">
          {username[0]?.toUpperCase() ?? '?'}
        </span>
        <FaChevronDown size={10} className="hidden text-muted-foreground sm:block" />
      </button>
      {open && (
        <div className="fixed inset-0 z-40" onClick={() => setOpen(false)}>
          <div
            className="absolute right-3 top-16 z-50 w-60 overflow-hidden rounded-xl border border-border bg-card text-card-foreground shadow-2xl"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="border-b border-border px-4 py-3">
              <p className="truncate text-sm font-bold">{username}</p>
              <p className="text-xs text-muted-foreground">Signed in</p>
            </div>
            <nav className="p-1.5 text-sm">
              {ACCOUNT_LINKS.map((l) => {
                const Icon = l.icon;
                return (
                  <Link
                    key={l.href}
                    href={l.href}
                    onClick={() => setOpen(false)}
                    className="flex items-center gap-3 rounded-lg px-3 py-2 font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  >
                    <Icon size={14} />
                    {l.label}
                  </Link>
                );
              })}
              <Link
                href="/account/notifications"
                onClick={() => setOpen(false)}
                className="flex items-center gap-3 rounded-lg px-3 py-2 font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                <FaBell size={14} />
                Notifications
                {unreadCount > 0 && (
                  <span className="ml-auto rounded-full bg-secondary px-1.5 text-[10px] font-bold text-white">{unreadCount}</span>
                )}
              </Link>
              <div className="my-1 border-t border-border" />
              <button
                onClick={() => { setOpen(false); onLogout(); }}
                className="flex w-full items-center gap-3 rounded-lg px-3 py-2 text-left font-medium text-muted-foreground transition-colors hover:bg-muted hover:text-destructive"
              >
                <FaSignOutAlt size={14} />
                Log out
              </button>
            </nav>
          </div>
        </div>
      )}
    </div>
  );
}

export function SiteHeader() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();
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
      <header className="sticky top-0 z-50 h-16 border-b border-border bg-sidebar/95 text-sidebar-foreground backdrop-blur-md">
        <div className="flex h-full items-center gap-3 px-3 sm:px-5">
          <Logo />

          <nav className="ml-4 hidden items-center gap-1 md:flex">
            {PRODUCT_TABS.map((t) => {
              const Icon = t.icon;
              const active = pathname.startsWith(t.href);
              return (
                <Link
                  key={t.href}
                  href={t.href}
                  className={`relative flex h-16 items-center gap-2 px-3 text-sm font-bold transition-colors ${
                    active ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
                  }`}
                >
                  <Icon size={16} className={active ? 'text-secondary' : ''} />
                  {t.label}
                  {active && <span className="absolute inset-x-3 bottom-0 h-[3px] rounded-t-full bg-secondary" />}
                </Link>
              );
            })}
          </nav>

          <div className="ml-auto flex items-center gap-1.5 sm:gap-2">
            {user ? (
              <>
                {/* Joined balance + deposit control, as on most betting sites. */}
                <div className="flex h-10 items-stretch overflow-hidden rounded-lg border border-border bg-background/60">
                  <Link
                    href="/account/wallet"
                    className="flex items-center gap-2 px-2.5 text-sm font-bold tabular-nums transition-colors hover:bg-muted sm:px-3"
                    title="Wallet"
                  >
                    <FaWallet size={13} className="text-secondary" />
                    <span>{formatBalance(wallet?.balance)}</span>
                    <span className="hidden text-xs font-semibold text-muted-foreground sm:inline">{wallet?.currency ?? ''}</span>
                  </Link>
                  <button
                    onClick={() => setDepositOpen(true)}
                    className="bg-win px-3 text-xs font-extrabold text-win-foreground transition-opacity hover:opacity-90 sm:px-4 sm:text-sm"
                  >
                    Deposit
                  </button>
                </div>
                <Link
                  href="/account/notifications"
                  aria-label="Notifications"
                  className="relative hidden h-10 w-10 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground sm:flex"
                >
                  <FaBell size={15} />
                  {unreadCount > 0 && (
                    <span className="absolute right-1.5 top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-live px-1 text-[10px] font-bold text-white">
                      {unreadCount > 9 ? '9+' : unreadCount}
                    </span>
                  )}
                </Link>
                <div className="hidden lg:block">
                  <SettingsMenu />
                </div>
                <UserMenu username={user.username} unreadCount={unreadCount} onLogout={handleLogout} />
              </>
            ) : (
              <>
                <div className="hidden lg:block">
                  <SettingsMenu />
                </div>
                <Link
                  href="/login"
                  className="flex h-10 items-center rounded-lg px-3 text-sm font-bold text-foreground transition-colors hover:bg-muted sm:px-4"
                >
                  Log in
                </Link>
                <Link
                  href="/register"
                  className="flex h-10 items-center rounded-lg bg-win px-4 text-sm font-extrabold text-win-foreground shadow transition-opacity hover:opacity-90 sm:px-5"
                >
                  Register
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
