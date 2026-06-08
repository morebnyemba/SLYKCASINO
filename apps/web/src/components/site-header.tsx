'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';

const links = [
  { href: '/', label: 'Lobby' },
  { href: '/sportsbook', label: 'Sportsbook' },
  { href: '/casino', label: 'Casino' },
  { href: '/promotions', label: 'Promotions' },
  { href: '/livechat', label: 'Live Chat' },
];

const authedLinks = [
  { href: '/account/wallet', label: 'Wallet' },
  { href: '/account/bets', label: 'My Bets' },
];

export function SiteHeader() {
  const { user, logout } = useAuth();
  const router = useRouter();

  async function handleLogout() {
    await logout();
    router.push('/login');
  }

  return (
    <header className="flex items-center gap-6 border-b border-border bg-card px-6 py-3">
      <Link href="/" className="text-lg font-bold">🎰 SLYK</Link>
      <nav className="flex flex-1 gap-4 text-sm">
        {links.map((l) => (
          <Link key={l.href} href={l.href} className="text-muted-foreground transition-colors hover:text-foreground">
            {l.label}
          </Link>
        ))}
        {user && authedLinks.map((l) => (
          <Link key={l.href} href={l.href} className="text-muted-foreground transition-colors hover:text-foreground">
            {l.label}
          </Link>
        ))}
      </nav>
      {user ? (
        <div className="flex items-center gap-3 text-sm">
          <Link href="/account/profile" className="font-medium hover:text-primary">
            {user.username}
          </Link>
          <button
            onClick={handleLogout}
            className="text-muted-foreground hover:text-foreground"
          >
            Log out
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-3 text-sm">
          <Link href="/login" className="text-muted-foreground hover:text-foreground">Log in</Link>
          <Link href="/register" className="rounded-md bg-primary px-3 py-1 text-primary-foreground text-xs font-medium hover:opacity-90">
            Sign up
          </Link>
        </div>
      )}
    </header>
  );
}
