'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useEffect } from 'react';
import { useAuth } from '@/lib/auth-context';

const tabs = [
  { href: '/account/profile', label: 'Profile' },
  { href: '/account/wallet', label: 'Wallet' },
  { href: '/account/bets', label: 'My Bets' },
  { href: '/account/casino', label: 'Casino History' },
];

export default function AccountLayout({ children }: { children: React.ReactNode }) {
  const { user, isLoading } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (!isLoading && !user) {
      router.replace('/login?next=/account/profile');
    }
  }, [user, isLoading, router]);

  if (isLoading) {
    return (
      <div className="flex min-h-[40vh] items-center justify-center text-muted-foreground text-sm">
        Loading…
      </div>
    );
  }

  if (!user) return null;

  return (
    <div className="grid gap-6 md:grid-cols-[180px_1fr]">
      <nav className="flex flex-col gap-2 text-sm">
        {tabs.map((t) => (
          <Link key={t.href} href={t.href} className="text-muted-foreground transition-colors hover:text-foreground">
            {t.label}
          </Link>
        ))}
      </nav>
      <section>{children}</section>
    </div>
  );
}
