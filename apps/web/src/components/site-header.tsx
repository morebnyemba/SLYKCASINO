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
    <header className="flex items-center gap-6 border-b border-border bg-primary px-6 py-3 shadow-sm">
      <Link href="/" className="text-lg font-bold text-white tracking-wide">🎰 SLYK</Link>
      <nav className="flex flex-1 gap-4 text-sm">
        {links.map((l) => (
          <Link key={l.href} href={l.href} className="text-white/75 transition-colors hover:text-white font-medium">
            {l.label}
          </Link>
        ))}
        {user && authedLinks.map((l) => (
          <Link key={l.href} href={l.href} className="text-white/75 transition-colors hover:text-white font-medium">
            {l.label}
          </Link>
        ))}
      </nav>
      {user ? (
        <div className="flex items-center gap-3 text-sm">
          <Link href="/account/profile" className="font-semibold text-white hover:text-white/80">
            {user.username}
          </Link>
          <button
            onClick={handleLogout}
            className="text-white/70 hover:text-white text-xs"
          >
            Log out
          </button>
        </div>
      ) : (
        <div className="flex items-center gap-3 text-sm">
          <Link href="/login" className="text-white/75 hover:text-white font-medium">Log in</Link>
          <Link href="/register" className="rounded-md bg-secondary px-3 py-1.5 text-white text-xs font-semibold hover:opacity-90 shadow">
            Sign up
          </Link>
        </div>
      )}
    </header>
  );
}
