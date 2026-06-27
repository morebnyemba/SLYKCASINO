'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { BsGrid1X2Fill } from 'react-icons/bs';
import { FaRegCommentDots, FaGift, FaImages, FaUsers, FaCalendarAlt, FaSignOutAlt, FaChartLine, FaIdCard, FaExchangeAlt, FaHistory } from 'react-icons/fa';
import { GiPerspectiveDiceSixFacesRandom } from 'react-icons/gi';
import type { IconType } from 'react-icons';
import { useAuth } from '@/lib/auth-context';
import { ThemeToggle } from '@/components/theme-toggle';

// hrefs omit the /admin-portal prefix — Next.js basePath prepends it and Nginx
// routes /admin-portal to this app.
const nav: { href: string; label: string; icon: IconType }[] = [
  { href: '/', label: 'Overview', icon: BsGrid1X2Fill },
  { href: '/livechat', label: 'Live Chat Console', icon: FaRegCommentDots },
  { href: '/betting-feeds', label: 'Betting Feeds', icon: FaChartLine },
  { href: '/promotions', label: 'Promotions', icon: FaGift },
  { href: '/banners', label: 'Site Banners', icon: FaImages },
  { href: '/users', label: 'Players', icon: FaUsers },
  { href: '/kyc', label: 'KYC Review', icon: FaIdCard },
  { href: '/transactions', label: 'Transactions', icon: FaExchangeAlt },
  { href: '/events', label: 'Events', icon: FaCalendarAlt },
  { href: '/audit-log', label: 'Audit Log', icon: FaHistory },
];

export function Sidebar() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const pathname = usePathname();

  async function handleLogout() {
    await logout();
    router.push('/login');
  }

  return (
    <aside className="flex min-h-screen w-56 flex-col gap-6 border-r border-gold/15 bg-gradient-to-b from-primary to-primary/90 p-5">
      <Link href="/" className="flex items-center gap-2">
        <span className="flex items-center gap-1 rounded-md bg-gradient-to-br from-gold to-gold/70 px-2.5 py-1 text-sm font-black tracking-wide text-[#1A1538] shadow-inner shadow-black/30 ring-1 ring-white/15">
          <GiPerspectiveDiceSixFacesRandom size={14} />
          SL<span className="relative -mr-px">Ý</span>K
        </span>
        <span className="text-sm font-bold text-white">Admin</span>
      </Link>
      <nav className="flex flex-col gap-1 text-sm">
        {nav.map((n) => {
          const Icon = n.icon;
          const active = pathname === n.href;
          return (
            <Link
              key={n.href}
              href={n.href}
              className={`group flex items-center gap-2.5 rounded-xl px-3 py-2.5 font-medium transition-all duration-150 ${
                active
                  ? 'bg-white/10 text-white shadow-[inset_2px_0_0_var(--gold)]'
                  : 'text-white/65 hover:bg-white/5 hover:text-white'
              }`}
            >
              <Icon size={14} className={active ? 'text-gold' : 'opacity-70 group-hover:opacity-100'} />
              {n.label}
            </Link>
          );
        })}
      </nav>
      <div className="mt-auto flex flex-col gap-3 border-t border-white/10 pt-4 text-xs text-white/60">
        <ThemeToggle className="text-white/65 hover:text-white" />
        {user && (
          <div className="flex items-center justify-between">
            <span className="font-semibold text-white">{user.username}</span>
            <button onClick={handleLogout} aria-label="Log out" title="Log out" className="flex items-center gap-1 hover:text-white">
              <FaSignOutAlt size={11} />
            </button>
          </div>
        )}
        <div>
          Raw DB →{' '}
          <a href="/django-admin/" className="text-gold underline-offset-4 hover:underline">Django Admin</a>
        </div>
      </div>
    </aside>
  );
}
