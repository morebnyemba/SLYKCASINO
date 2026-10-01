'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { FaUser, FaWallet, FaShieldAlt, FaIdCard, FaBell, FaSignOutAlt, FaHandshake } from 'react-icons/fa';
import { GiTrophy, GiRollingDices } from 'react-icons/gi';
import type { IconType } from 'react-icons';
import { useAuth } from '@/lib/auth-context';
import { ThemeToggle, SettingsMenu } from '@/components/settings-menu';
import { LoadingState } from '@slyk/ui/components/spinner';

const tabs: { href: string; label: string; icon: IconType }[] = [
  { href: '/account/profile', label: 'Profile', icon: FaUser },
  { href: '/account/wallet', label: 'Wallet', icon: FaWallet },
  { href: '/account/bets', label: 'My Bets', icon: GiTrophy },
  { href: '/account/casino', label: 'Casino History', icon: GiRollingDices },
  { href: '/account/verification', label: 'Verification', icon: FaIdCard },
  { href: '/account/notifications', label: 'Notifications', icon: FaBell },
  { href: '/account/affiliate', label: 'Refer & earn', icon: FaHandshake },
  { href: '/account/settings', label: 'Responsible gaming', icon: FaShieldAlt },
];

export default function AccountLayout({ children }: { children: React.ReactNode }) {
  const { user, logout, isLoading } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace('/login?next=/account/profile');
    }
  }, [user, isLoading, router]);

  async function handleLogout() {
    await logout();
    router.push('/login');
  }

  if (isLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-muted-foreground text-sm">
        <LoadingState />
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="grid grid-cols-[minmax(0,1fr)] gap-4 md:grid-cols-[230px_minmax(0,1fr)] md:gap-6">
      {/* Mobile: compact player card + swipeable tab strip */}
      <div className="min-w-0 space-y-3 md:hidden">
        <div className="flex items-center gap-3 rounded-2xl border border-border bg-card p-3">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-gold to-gold/70 text-base font-black text-gold-foreground">
            {user.username?.[0]?.toUpperCase() ?? '?'}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-extrabold">{user.username}</p>
            <p className="text-xs text-muted-foreground">My account</p>
          </div>
          <button
            onClick={handleLogout}
            aria-label="Log out"
            className="flex h-10 w-10 items-center justify-center rounded-xl text-muted-foreground hover:bg-muted hover:text-destructive"
          >
            <FaSignOutAlt size={15} />
          </button>
        </div>
        <nav className="sticky top-[var(--header-h)] z-20 -mx-3 border-b border-border bg-background/95 px-3 backdrop-blur">
          <div className="no-scrollbar flex gap-1 overflow-x-auto">
            {tabs.map((t) => {
              const Icon = t.icon;
              const active = pathname === t.href;
              return (
                <Link
                  key={t.href}
                  href={t.href}
                  className={`relative flex shrink-0 items-center gap-1.5 px-3 py-3 text-[13px] font-bold transition-colors ${
                    active ? 'text-foreground' : 'text-muted-foreground'
                  }`}
                >
                  <Icon size={13} className={active ? 'text-secondary' : ''} />
                  {t.label}
                  {active && <span className="absolute inset-x-2 bottom-0 h-[3px] rounded-t-full bg-secondary" />}
                </Link>
              );
            })}
          </div>
        </nav>
      </div>

      <aside className="hidden h-fit rounded-2xl border border-border bg-card p-3 shadow-sm md:sticky md:top-[calc(var(--header-h)+1rem)] md:block">
        <div className="mb-2 flex items-center gap-3 rounded-xl px-2 py-2.5">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-gold to-gold/70 text-base font-bold text-gold-foreground shadow-inner shadow-black/10">
            {user.username?.[0]?.toUpperCase() ?? '?'}
          </span>
          <div className="min-w-0 flex-1">
            <p className="truncate text-sm font-semibold">{user.username}</p>
            <p className="text-xs text-muted-foreground">My Account</p>
          </div>
          <ThemeToggle className="!h-8 !w-8 !gap-0 !px-0 !text-muted-foreground hover:!bg-muted/40 hover:!text-foreground [&>span]:hidden" />
          <SettingsMenu className="!h-8 !w-8 !text-muted-foreground hover:!bg-muted/40 hover:!text-foreground" />
        </div>
        <nav className="flex flex-col gap-1 text-sm">
          {tabs.map((t) => {
            const Icon = t.icon;
            const active = pathname === t.href;
            return (
              <Link
                key={t.href}
                href={t.href}
                className={`group flex items-center gap-2.5 rounded-xl px-3 py-2.5 font-medium transition-all duration-150 ${
                  active
                    ? 'bg-gradient-to-r from-gold/15 to-transparent text-foreground shadow-[inset_2px_0_0_var(--gold)]'
                    : 'text-muted-foreground hover:bg-muted/40 hover:text-foreground'
                }`}
              >
                <Icon size={15} className={active ? 'text-gold' : 'opacity-70 transition-opacity group-hover:opacity-100'} />
                {t.label}
              </Link>
            );
          })}
          <button
            onClick={handleLogout}
            className="mt-1 flex items-center gap-2.5 rounded-xl border-t border-border px-3 py-2.5 pt-3.5 text-left font-medium text-muted-foreground transition-colors hover:text-foreground"
          >
            <FaSignOutAlt size={15} className="opacity-70" />
            Log out
          </button>
        </nav>
      </aside>
      <section className="min-w-0">{children}</section>
    </div>
  );
}
