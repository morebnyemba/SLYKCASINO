'use client';

import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { useAuth } from '@/lib/auth-context';

// hrefs omit the /admin-portal prefix — Next.js basePath prepends it and Nginx
// routes /admin-portal to this app.
const nav = [
  { href: '/', label: 'Overview' },
  { href: '/livechat', label: 'Live Chat Console' },
  { href: '/betting-feeds', label: 'Betting Feeds' },
  { href: '/promotions', label: 'Promotions' },
  { href: '/banners', label: 'Site Banners' },
  { href: '/users', label: 'Players' },
  { href: '/events', label: 'Events' },
];

export function Sidebar() {
  const { user, logout } = useAuth();
  const router = useRouter();

  async function handleLogout() {
    await logout();
    router.push('/login');
  }

  return (
    <aside className="flex min-h-screen w-56 flex-col gap-6 border-r border-border bg-primary p-5">
      <div className="text-base font-bold text-white">🛡️ SLYK Admin</div>
      <nav className="flex flex-col gap-2 text-sm">
        {nav.map((n) => (
          <Link key={n.href} href={n.href} className="text-white/70 transition-colors hover:text-white font-medium">
            {n.label}
          </Link>
        ))}
      </nav>
      <div className="mt-auto flex flex-col gap-3 text-xs text-white/60">
        {user && (
          <div className="flex items-center justify-between">
            <span className="font-semibold text-white">{user.username}</span>
            <button onClick={handleLogout} className="hover:text-white">Log out</button>
          </div>
        )}
        <div>
          Raw DB →{' '}
          <a href="/django-admin/" className="text-secondary underline-offset-4 hover:underline">Django Admin</a>
        </div>
      </div>
    </aside>
  );
}
