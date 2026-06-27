'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { FaUser, FaWallet, FaShieldAlt, FaIdCard, FaBell, FaSignOutAlt } from 'react-icons/fa';
import { GiTrophy, GiRollingDices } from 'react-icons/gi';
import type { IconType } from 'react-icons';
import { useAuth } from '@/lib/auth-context';
import { ThemeToggle, SettingsMenu } from '@/components/settings-menu';

const tabs: { href: string; label: string; icon: IconType }[] = [
  { href: '/account/profile', label: 'Profile', icon: FaUser },
  { href: '/account/wallet', label: 'Wallet', icon: FaWallet },
  { href: '/account/bets', label: 'My Bets', icon: GiTrophy },
  { href: '/account/casino', label: 'Casino History', icon: GiRollingDices },
  { href: '/account/verification', label: 'Verification', icon: FaIdCard },
  { href: '/account/notifications', label: 'Notifications', icon: FaBell },
  { href: '/account/settings', label: 'Responsible Gambling', icon: FaShieldAlt },
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
        Loading…
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="grid gap-6 md:grid-cols-[220px_1fr]">
      <aside className="h-fit rounded-2xl border border-gold/20 bg-card/60 p-3 shadow-sm backdrop-blur-sm">
        <div className="mb-2 flex items-center gap-3 rounded-xl px-2 py-2.5">
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-gold to-gold/70 text-base font-bold text-[#1A1538] shadow-inner shadow-black/10">
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
      <section>{children}</section>
    </div>
  );
}
