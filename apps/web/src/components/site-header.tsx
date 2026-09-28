'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import { GiTrophy, GiRollingDices } from 'react-icons/gi';
import {
  FaUser, FaSignOutAlt, FaWallet, FaBell, FaIdCard, FaShieldAlt, FaChevronDown, FaHistory, FaPlus, FaGift,
} from 'react-icons/fa';
import { BsSearch, BsTicketPerforated } from 'react-icons/bs';
import type { IconType } from 'react-icons';
import { useAuth } from '@/lib/auth-context';
import { useApi } from '@/lib/use-api';
import { useShell } from '@/lib/shell-context';
import { Logo } from '@/components/logo';
import { Portal } from '@/components/portal';
import { SettingsMenu, ThemeToggle } from '@/components/settings-menu';
import { DepositModal } from '@/components/deposit-modal';

interface Wallet {
  balance?: string;
  currency?: string;
}

interface Notification {
  id: number;
  read: boolean;
}

const ACCOUNT_LINKS: { href: string; label: string; icon: IconType }[] = [
  { href: '/account/profile', label: 'Profile', icon: FaUser },
  { href: '/account/wallet', label: 'Wallet', icon: FaWallet },
  { href: '/account/bets', label: 'My bets', icon: BsTicketPerforated },
  { href: '/account/casino', label: 'Casino history', icon: FaHistory },
  { href: '/promotions', label: 'Promotions', icon: FaGift },
  { href: '/account/verification', label: 'Verification', icon: FaIdCard },
  { href: '/account/settings', label: 'Responsible gaming', icon: FaShieldAlt },
];

function formatBalance(balance?: string): string {
  if (balance == null) return '—';
  const n = Number(balance);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : balance;
}

const iconBtn =
  'relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-muted hover:text-foreground';

/** Casino | Sports segmented switch — the primary product toggle on betting sites. */
function ProductSwitch() {
  const pathname = usePathname();
  const onSports = pathname.startsWith('/sportsbook');
  const onCasino = pathname.startsWith('/casino');
  const item = (active: boolean) =>
    `flex h-9 items-center gap-2 rounded-[10px] px-4 text-[13px] font-extrabold transition-all ${
      active ? 'bg-secondary text-white shadow-[0_4px_14px_color-mix(in_srgb,var(--secondary)_40%,transparent)]' : 'text-muted-foreground hover:text-foreground'
    }`;
  return (
    <div className="hidden shrink-0 items-center gap-1 rounded-xl border border-border bg-background/60 p-1 md:flex">
      <Link href="/casino" className={item(onCasino)}><GiRollingDices size={16} /> Casino</Link>
      <Link href="/sportsbook" className={item(onSports)}><GiTrophy size={15} /> Sports</Link>
    </div>
  );
}

function SearchTrigger() {
  const { setSearchOpen } = useShell();
  return (
    <>
      {/* Wide field-style trigger on larger screens… */}
      <button
        onClick={() => setSearchOpen(true)}
        className="hidden h-10 min-w-0 max-w-sm flex-1 items-center gap-2.5 rounded-xl border border-border bg-background/60 px-3.5 text-sm text-muted-foreground transition-colors hover:border-secondary/50 hover:text-foreground xl:flex"
      >
        <BsSearch size={14} className="shrink-0" />
        <span className="truncate">Search games or matches</span>
        <kbd className="ml-auto rounded-md border border-border bg-muted px-1.5 text-[10px] font-bold">/</kbd>
      </button>
      {/* …icon button elsewhere. */}
      <button onClick={() => setSearchOpen(true)} aria-label="Search" className={`${iconBtn} xl:hidden`}>
        <BsSearch size={16} />
      </button>
    </>
  );
}

function WalletControl({ wallet, onDeposit }: { wallet: Wallet | null; onDeposit: () => void }) {
  return (
    <div className="flex h-10 min-w-0 items-stretch overflow-hidden rounded-xl border border-border bg-background/60">
      <Link
        href="/account/wallet"
        title="Wallet"
        className="flex min-w-0 items-center gap-2 px-2.5 transition-colors hover:bg-muted sm:px-3"
      >
        <FaWallet size={13} className="hidden shrink-0 text-secondary min-[380px]:block" />
        <span className="flex min-w-0 flex-col leading-none">
          <span className="truncate text-[13px] font-extrabold tabular-nums sm:text-sm">{formatBalance(wallet?.balance)}</span>
          <span className="mt-0.5 text-[9.5px] font-bold uppercase tracking-wide text-muted-foreground 2xl:hidden">{wallet?.currency ?? 'Balance'}</span>
        </span>
        <span className="hidden text-xs font-bold text-muted-foreground 2xl:inline">{wallet?.currency ?? ''}</span>
      </Link>
      <button
        onClick={onDeposit}
        aria-label="Deposit"
        className="flex items-center gap-1.5 bg-win px-3 text-xs font-extrabold text-win-foreground transition-opacity hover:opacity-90 sm:px-4 sm:text-sm"
      >
        <FaPlus size={11} className="sm:hidden" />
        <span className="hidden sm:inline">Deposit</span>
      </button>
    </div>
  );
}

function UserMenu({ username, unreadCount, onLogout, onDeposit }: {
  username: string; unreadCount: number; onLogout: () => void; onDeposit: () => void;
}) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  useEffect(() => { setOpen(false); }, [pathname]);

  return (
    <div className="relative shrink-0">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Account menu"
        aria-expanded={open}
        className="flex h-10 items-center gap-1.5 rounded-xl pl-0.5 pr-1 transition-colors hover:bg-muted sm:pr-2"
      >
        <span className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-secondary to-primary text-sm font-black text-white">
          {username[0]?.toUpperCase() ?? '?'}
          {unreadCount > 0 && <span className="absolute -right-0.5 -top-0.5 h-2.5 w-2.5 rounded-full border-2 border-sidebar bg-live sm:hidden" />}
        </span>
        <FaChevronDown size={9} className={`hidden text-muted-foreground transition-transform sm:block ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && (
        <Portal>
        <div className="fixed inset-0 z-[60] bg-black/50 sm:bg-transparent" onClick={() => setOpen(false)}>
          <div
            className="animate-slyk-sheet absolute inset-x-0 bottom-0 max-h-[85vh] overflow-y-auto rounded-t-3xl border border-border bg-card pb-[max(env(safe-area-inset-bottom),0.75rem)] text-card-foreground shadow-2xl sm:inset-x-auto sm:bottom-auto sm:right-3 sm:top-[calc(var(--header-h)+0.25rem)] sm:w-72 sm:animate-none sm:rounded-2xl sm:pb-0"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-center pt-2 sm:hidden"><span className="h-[5px] w-10 rounded-full bg-border" /></div>
            <div className="flex items-center gap-3 border-b border-border px-4 py-3.5">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-secondary to-primary font-black text-white">
                {username[0]?.toUpperCase() ?? '?'}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-extrabold">{username}</p>
                <Link href="/account/profile" className="text-xs font-semibold text-secondary hover:underline">View profile</Link>
              </div>
              <button
                onClick={() => { setOpen(false); onDeposit(); }}
                className="rounded-lg bg-win px-3 py-1.5 text-xs font-extrabold text-win-foreground"
              >
                Deposit
              </button>
            </div>
            <nav className="p-1.5 text-sm">
              {ACCOUNT_LINKS.map((l) => {
                const Icon = l.icon;
                return (
                  <Link
                    key={l.href}
                    href={l.href}
                    className="flex items-center gap-3 rounded-xl px-3 py-2.5 font-semibold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
                  >
                    <Icon size={14} />
                    {l.label}
                  </Link>
                );
              })}
              <Link
                href="/account/notifications"
                className="flex items-center gap-3 rounded-xl px-3 py-2.5 font-semibold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
              >
                <FaBell size={14} />
                Notifications
                {unreadCount > 0 && (
                  <span className="ml-auto rounded-full bg-live px-1.5 text-[10px] font-bold text-white">{unreadCount}</span>
                )}
              </Link>
              <div className="my-1 flex items-center gap-1 border-t border-border pt-1 lg:hidden">
                <ThemeToggle className="flex-1" />
                <SettingsMenu placement="header" />
              </div>
              <div className="my-1 border-t border-border" />
              <button
                onClick={() => { setOpen(false); onLogout(); }}
                className="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left font-semibold text-muted-foreground transition-colors hover:bg-destructive/10 hover:text-destructive"
              >
                <FaSignOutAlt size={14} />
                Log out
              </button>
            </nav>
          </div>
        </div>
        </Portal>
      )}
    </div>
  );
}

export function SiteHeader() {
  const { user, logout, isLoading } = useAuth();
  const router = useRouter();
  const [depositOpen, setDepositOpen] = useState(false);
  const [scrolled, setScrolled] = useState(false);
  const { data: wallet } = useApi<Wallet>(user ? '/wallet/' : null);
  const { data: notifications } = useApi<Notification[]>(user ? '/notifications/' : null);
  const unreadCount = notifications?.filter((n) => !n.read).length ?? 0;

  // Lift the header off the page once content scrolls under it.
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  async function handleLogout() {
    await logout();
    router.push('/login');
  }

  return (
    <>
      {/* Mobile: truly fixed (sticky is unreliable in some mobile browsers and would let the
          header slide under the notch in the installed PWA). Desktop: sticky within the
          content column next to the nav rail. The spacer keeps content clear of it. */}
      <div aria-hidden className="h-[var(--header-h)] shrink-0 lg:hidden" />
      <header
        className={`fixed inset-x-0 top-0 z-50 border-b bg-sidebar/95 pt-[var(--safe-top)] text-sidebar-foreground backdrop-blur-xl transition-shadow lg:sticky lg:inset-x-auto lg:pt-0 ${
          scrolled ? 'border-border shadow-[0_8px_24px_rgba(0,0,0,0.25)]' : 'border-border/60'
        }`}
      >
        <div className="flex h-16 items-center gap-2 px-3 sm:gap-3 sm:px-4 lg:px-5">
          {/* The desktop rail carries the logo; smaller screens show it here. */}
          <div className="lg:hidden">
            <Logo markOnly={!!user} nameClassName="max-[399px]:hidden" />
          </div>

          <ProductSwitch />
          <SearchTrigger />

          <div className="ml-auto flex min-w-0 items-center gap-1.5 sm:gap-2">
            {isLoading ? (
              <div className="h-10 w-40 animate-pulse rounded-xl bg-muted" />
            ) : user ? (
              <>
                <WalletControl wallet={wallet} onDeposit={() => setDepositOpen(true)} />
                <Link href="/account/notifications" aria-label="Notifications" className={`${iconBtn} hidden sm:flex`}>
                  <FaBell size={15} />
                  {unreadCount > 0 && (
                    <span className="absolute right-1.5 top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-live px-1 text-[10px] font-bold text-white">
                      {unreadCount > 9 ? '9+' : unreadCount}
                    </span>
                  )}
                </Link>
                <UserMenu
                  username={user.username}
                  unreadCount={unreadCount}
                  onLogout={handleLogout}
                  onDeposit={() => setDepositOpen(true)}
                />
              </>
            ) : (
              <>
                <Link
                  href="/login"
                  className="flex h-10 items-center whitespace-nowrap rounded-xl px-2.5 text-sm font-bold text-foreground transition-colors hover:bg-muted sm:px-4"
                >
                  Log in
                </Link>
                <Link
                  href="/register"
                  className="flex h-10 items-center whitespace-nowrap rounded-xl bg-win px-4 text-sm font-extrabold text-win-foreground shadow-[0_4px_14px_color-mix(in_srgb,var(--win)_35%,transparent)] transition-opacity hover:opacity-90 sm:px-5"
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
