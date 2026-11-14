'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import {
  FaUser, FaSignOutAlt, FaWallet, FaBell, FaIdCard, FaShieldAlt, FaChevronDown, FaGift, FaHandshake,
} from 'react-icons/fa';
import {
  BsArrowLeftRight, BsCashStack, BsClockHistory, BsList, BsPlusCircle, BsReceipt, BsSearch, BsTicketPerforated,
} from 'react-icons/bs';
import type { IconType } from 'react-icons';
import { useAuth } from '@/lib/auth-context';
import { WALLET_CHANGED } from '@/components/cashout';
import { isAuthRoute } from '@/lib/auth-routes';
import { useApi } from '@/lib/use-api';
import { useShell } from '@/lib/shell-context';
import { Logo } from '@/components/logo';
import { Portal } from '@/components/portal';
import { useRailOpen } from '@/components/bet-rail';
import { useBetslip } from '@/lib/betslip-context';
import { SettingsMenu } from '@/components/settings-menu';
import { DepositModal } from '@/components/deposit-modal';

interface Wallet {
  balance?: string;
  currency?: string;
  wallets?: Record<'deposit' | 'bonus' | 'winnings', { balance: string }>;
}

interface Notification {
  id: number;
  read: boolean;
}

// Money and bets first (what players open the menu for), then the account.
const MONEY_LINKS: { href: string; label: string; icon: IconType }[] = [
  { href: '/account/wallet#withdraw', label: 'Withdraw', icon: BsCashStack },
  { href: '/account/bets?tab=open', label: 'Open bets', icon: BsTicketPerforated },
  { href: '/account/bets?tab=settled', label: 'Bet history', icon: BsClockHistory },
  { href: '/account/wallet#transactions', label: 'Transactions', icon: BsArrowLeftRight },
  { href: '/promotions', label: 'Bonus & promotions', icon: FaGift },
];
const ACCOUNT_LINKS: { href: string; label: string; icon: IconType }[] = [
  { href: '/account/profile', label: 'My account', icon: FaUser },
  { href: '/account/verification', label: 'Verification', icon: FaIdCard },
  { href: '/account/affiliate', label: 'Agent dashboard', icon: FaHandshake },
  { href: '/account/settings', label: 'Safety & limits', icon: FaShieldAlt },
];

function formatBalance(balance?: string): string {
  if (balance == null) return '—';
  const n = Number(balance);
  return Number.isFinite(n) ? n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : balance;
}

const iconBtn =
  'relative flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-muted-foreground transition-colors hover:bg-muted hover:text-foreground';

function MenuButton() {
  const { menuOpen, setMenuOpen } = useShell();
  return (
    <button onClick={() => setMenuOpen(!menuOpen)} aria-label="Menu" aria-expanded={menuOpen}
      className={`${iconBtn.replace('h-10 w-10', 'h-10 w-9')} -ml-1 lg:hidden`}>
      <BsList size={22} />
    </button>
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
        <span className="truncate">Search teams or matches</span>
        <kbd className="ml-auto rounded-md border border-border bg-muted px-1.5 text-[10px] font-bold">/</kbd>
      </button>
      {/* …icon button elsewhere (the narrowest phones search from the menu and the quick-nav chips). */}
      <button onClick={() => setSearchOpen(true)} aria-label="Search" className={`${iconBtn.replace('relative flex', 'relative hidden sm:flex')} xl:hidden`}>
        <BsSearch size={16} />
      </button>
    </>
  );
}

/** Desktop bet-slip toggle: shows/hides the right rail on xl, opens the slide-in slip below that. */
function SlipToggle() {
  const { legs, setSlipOpen } = useBetslip();
  const { setRailPref } = useShell();
  const railOpen = useRailOpen();
  return (
    <button
      onClick={() => {
        if (window.matchMedia('(min-width: 1280px)').matches) setRailPref(!railOpen);
        else setSlipOpen(true);
      }}
      aria-label="Bet slip"
      title="Bet slip"
      className={`${iconBtn} hidden lg:flex ${railOpen ? 'xl:bg-secondary/15 xl:text-foreground' : ''}`}
    >
      <BsReceipt size={16} />
      {legs.length > 0 && (
        <span className="absolute right-1 top-1 flex h-4 min-w-4 items-center justify-center rounded-full bg-win px-1 text-[10px] font-extrabold text-win-foreground">
          {legs.length}
        </span>
      )}
    </button>
  );
}

function WalletControl({ wallet, onDeposit }: { wallet: Wallet | null; onDeposit: () => void }) {
  return (
    <div className="flex h-10 min-w-0 items-stretch overflow-hidden rounded-xl border border-border bg-background/60">
      <Link
        href="/account/wallet"
        title={wallet?.wallets
          ? `Deposit ${wallet.wallets.deposit.balance} · Bonus ${wallet.wallets.bonus.balance} · Winnings ${wallet.wallets.winnings.balance}`
          : 'Wallet'}
        className="flex min-w-0 items-center gap-2 px-2.5 transition-colors hover:bg-muted sm:px-3"
      >
        <FaWallet size={13} className="hidden shrink-0 text-secondary sm:block" />
        <span className="flex min-w-0 flex-col leading-none">
          <span className="truncate text-[13px] font-extrabold tabular-nums sm:text-sm">{formatBalance(wallet?.balance)}</span>
          <span className="mt-0.5 text-[9.5px] font-bold uppercase tracking-wide text-muted-foreground 2xl:hidden">{wallet?.currency ?? 'Balance'}</span>
        </span>
        <span className="hidden text-xs font-bold text-muted-foreground 2xl:inline">{wallet?.currency ?? ''}</span>
      </Link>
      <button
        onClick={onDeposit}
        aria-label="Deposit"
        className="flex items-center gap-1.5 bg-win px-2.5 text-xs font-extrabold text-win-foreground transition-opacity hover:opacity-90 min-[390px]:px-3 sm:px-4 sm:text-sm"
      >
        <span>Deposit</span>
      </button>
    </div>
  );
}

const menuRow = 'flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left font-semibold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground';

function UserMenu({ username, unreadCount, onLogout, onDeposit, wallet }: {
  username: string; unreadCount: number; onLogout: () => void; onDeposit: () => void; wallet: Wallet | null;
}) {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  const { setSearchOpen } = useShell();
  useEffect(() => { setOpen(false); }, [pathname]);
  // A hash/query change on the same page (Bet history after Open bets) doesn't change the pathname.
  const close = () => setOpen(false);

  return (
    <div className="relative shrink-0">
      <button
        onClick={() => setOpen((v) => !v)}
        aria-label="Account menu"
        aria-expanded={open}
        className="flex h-10 items-center gap-1.5 rounded-xl pl-0.5 pr-1 transition-colors hover:bg-muted sm:pr-2"
      >
        <span className="relative flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-[#0B3BB8] text-sm font-black text-white">
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
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-gradient-to-br from-primary to-[#0B3BB8] font-black text-white">
                {username[0]?.toUpperCase() ?? '?'}
              </span>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-extrabold">{username}</p>
                <Link href="/account/profile" className="text-xs font-semibold text-secondary hover:underline">View profile</Link>
              </div>
            </div>
            {/* Balance card: the total, its three wallets, and Deposit. */}
            <div className="mx-3 mt-3 rounded-2xl bg-gradient-to-br from-primary to-[#0B3BB8] p-3.5 text-white">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="text-[10px] font-bold uppercase tracking-wide text-white/70">Balance</p>
                  <p className="truncate text-xl font-black tabular-nums">
                    {formatBalance(wallet?.balance)} <span className="text-xs font-bold text-white/70">{wallet?.currency ?? ''}</span>
                  </p>
                </div>
                <button
                  onClick={() => { close(); onDeposit(); }}
                  className="shrink-0 rounded-lg bg-win px-3.5 py-2 text-xs font-extrabold text-win-foreground"
                >
                  Deposit
                </button>
              </div>
              {wallet?.wallets && (
                <div className="mt-2.5 grid grid-cols-3 gap-1.5 text-[10.5px]">
                  {(['deposit', 'bonus', 'winnings'] as const).map((k) => (
                    <div key={k} className="rounded-lg bg-white/10 px-2 py-1.5">
                      <p className="font-semibold capitalize text-white/70">{k}</p>
                      <p className="font-extrabold tabular-nums">{formatBalance(wallet.wallets![k].balance)}</p>
                    </div>
                  ))}
                </div>
              )}
            </div>
            <nav className="p-1.5 text-sm">
              <button onClick={() => { close(); setSearchOpen(true); }} className={`${menuRow} sm:hidden`}>
                <BsSearch size={14} /> Search
              </button>
              <button onClick={() => { close(); onDeposit(); }} className={menuRow}>
                <BsPlusCircle size={14} /> Deposit
              </button>
              {MONEY_LINKS.map((l) => {
                const Icon = l.icon;
                return (
                  <Link key={l.href} href={l.href} onClick={close} className={menuRow}>
                    <Icon size={14} />
                    {l.label}
                  </Link>
                );
              })}
              <div className="my-1 border-t border-border" />
              {ACCOUNT_LINKS.map((l) => {
                const Icon = l.icon;
                return (
                  <Link key={l.href} href={l.href} onClick={close} className={menuRow}>
                    <Icon size={14} />
                    {l.label}
                  </Link>
                );
              })}
              <Link
                href="/account/notifications"
                onClick={close}
                className={menuRow}
              >
                <FaBell size={14} />
                Notifications
                {unreadCount > 0 && (
                  <span className="ml-auto rounded-full bg-live px-1.5 text-[10px] font-bold text-white">{unreadCount}</span>
                )}
              </Link>
              <div className="my-1 flex items-center gap-1 border-t border-border pt-1 lg:hidden">
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
  const { data: wallet, refetch: refetchWallet } = useApi<Wallet>(user ? '/wallet/' : null);
  // Placing a bet debits the wallet — refresh the balance shown here.
  const { status: slipStatus } = useBetslip();
  useEffect(() => {
    if (slipStatus && /placed|in-play/i.test(slipStatus)) refetchWallet();
  }, [slipStatus, refetchWallet]);
  // A cash-out credits the wallet from elsewhere on the page.
  useEffect(() => {
    const onChange = () => refetchWallet();
    window.addEventListener(WALLET_CHANGED, onChange);
    return () => window.removeEventListener(WALLET_CHANGED, onChange);
  }, [refetchWallet]);
  const { data: notifications } = useApi<Notification[]>(user ? '/notifications/' : null);
  const unreadCount = notifications?.filter((n) => !n.read).length ?? 0;

  // Lift the header off the page once content scrolls under it.
  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 4);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  const onAuthPage = isAuthRoute(usePathname());

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
          {/* The desktop rail carries the logo; smaller screens (and the rail-less
              sign-in pages) show it here. */}
          {/* Phones/tablets: the menu drawer (sports, games, promotions…) opens from here. */}
          {!onAuthPage && <MenuButton />}
          <div className={onAuthPage ? '' : 'lg:hidden'}>
            {/* The wordmark shows on every screen (a little smaller on the narrowest
                phones); search lives in the bottom bar on phones, leaving room for it. */}
            <Logo imgClassName="h-9 max-[389px]:h-7 sm:h-10" />
          </div>

          <SearchTrigger />

          <div className="ml-auto flex min-w-0 items-center gap-1.5 sm:gap-2">
            <SlipToggle />
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
                  wallet={wallet}
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
