'use client';

import Link from 'next/link';
import { usePathname, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import type { IconType } from 'react-icons';
import {
  BsActivity, BsBroadcast, BsCalendar2Week, BsCashStack, BsChatDots, BsClockHistory, BsGift, BsGrid1X2,
  BsImages, BsList, BsMoonStars, BsPalette, BsPeople, BsPersonBadge, BsBoxArrowRight, BsSun, BsTicketPerforated,
  BsTrophy, BsXLg, BsDiagram3, BsDatabase, BsCreditCard2Front,
} from 'react-icons/bs';
import { GiPerspectiveDiceSixFacesRandom } from 'react-icons/gi';
import { useAuth } from '@/lib/auth-context';
import { useSiteIdentity } from '@/lib/identity-context';
import { useTheme } from '@/lib/theme-context';
import { useApi } from '@/lib/use-api';
import { cx } from '@/components/console/ui';

type Badge = 'kyc' | 'live' | 'commissions' | 'settle';

interface NavItem { href: string; label: string; icon: IconType; badge?: Badge; match?: string[] }
interface NavSection { title: string; items: NavItem[] }

// hrefs omit the /admin-portal prefix — Next.js basePath prepends it.
export const NAV: NavSection[] = [
  { title: 'Operations', items: [
    { href: '/', label: 'Dashboard', icon: BsGrid1X2 },
    { href: '/livechat', label: 'Live chat', icon: BsChatDots },
  ] },
  { title: 'Sportsbook', items: [
    { href: '/sportsbook/matches', label: 'Matches', icon: BsCalendar2Week, badge: 'live', match: ['/sportsbook/matches', '/events'] },
    { href: '/sportsbook/leagues', label: 'Leagues', icon: BsTrophy },
    { href: '/betting-feeds', label: 'Bets & tickets', icon: BsTicketPerforated, badge: 'settle' },
    { href: '/sportsbook/feed', label: 'Odds feed', icon: BsBroadcast },
  ] },
  { title: 'Players', items: [
    { href: '/users', label: 'Players', icon: BsPeople, match: ['/users', '/players'] },
    { href: '/kyc', label: 'KYC review', icon: BsPersonBadge, badge: 'kyc' },
  ] },
  { title: 'Money', items: [
    { href: '/transactions', label: 'Transactions', icon: BsCashStack },
    { href: '/payment-methods', label: 'Payment methods', icon: BsCreditCard2Front },
    { href: '/affiliates', label: 'Affiliates', icon: BsDiagram3, badge: 'commissions' },
  ] },
  { title: 'Marketing', items: [
    { href: '/promotions', label: 'Promotions', icon: BsGift },
    { href: '/banners', label: 'Banners', icon: BsImages },
  ] },
  { title: 'Settings', items: [
    { href: '/branding', label: 'Branding', icon: BsPalette },
    { href: '/audit-log', label: 'Audit log', icon: BsClockHistory },
  ] },
];

export function isActive(pathname: string, item: NavItem) {
  const roots = item.match ?? [item.href];
  return roots.some((r) => (r === '/' ? pathname === '/' : pathname === r || pathname.startsWith(`${r}/`)));
}

interface NavStats {
  queues?: { kyc_pending?: number; commissions_pending?: number; markets_to_settle?: number };
  sportsbook?: { live?: number };
}

function NavLinks({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = usePathname();
  const { data } = useApi<NavStats>('/admin/stats/');
  const counts: Record<Badge, number> = {
    kyc: data?.queues?.kyc_pending ?? 0,
    live: data?.sportsbook?.live ?? 0,
    commissions: data?.queues?.commissions_pending ?? 0,
    settle: data?.queues?.markets_to_settle ?? 0,
  };
  return (
    <nav className="flex flex-col gap-5">
      {NAV.map((section) => (
        <div key={section.title}>
          <p className="mb-1.5 px-3 text-[10.5px] font-bold uppercase tracking-[0.16em] text-white/35">{section.title}</p>
          <div className="flex flex-col gap-0.5">
            {section.items.map((item) => {
              const Icon = item.icon;
              const active = isActive(pathname, item);
              const count = item.badge ? counts[item.badge] : 0;
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  onClick={onNavigate}
                  className={cx(
                    'group relative flex items-center gap-3 rounded-xl px-3 py-2 text-[13.5px] font-medium transition-colors',
                    active ? 'bg-white/[0.09] text-white' : 'text-white/60 hover:bg-white/[0.05] hover:text-white',
                  )}
                >
                  {active && <span className="absolute inset-y-1.5 left-0 w-[3px] rounded-r-full bg-gradient-to-b from-[#8f88ff] to-secondary" />}
                  <Icon size={15} className={active ? 'text-[#a7a2ff]' : 'opacity-70 group-hover:opacity-100'} />
                  <span className="flex-1 truncate">{item.label}</span>
                  {count > 0 && (
                    <span className={cx(
                      'min-w-5 rounded-full px-1.5 py-px text-center text-[10.5px] font-bold tabular-nums',
                      item.badge === 'live' ? 'bg-live text-white' : 'bg-white/15 text-white',
                    )}>
                      {count > 99 ? '99+' : count}
                    </span>
                  )}
                </Link>
              );
            })}
          </div>
        </div>
      ))}
    </nav>
  );
}

function Brand() {
  const identity = useSiteIdentity();
  return (
    <Link href="/" className="flex min-w-0 items-center gap-2.5">
      {identity.logo_url ? (
        // eslint-disable-next-line @next/next/no-img-element
        <img src={identity.logo_url} alt={identity.site_name} className="h-8 w-auto max-w-[120px] shrink-0 object-contain" />
      ) : (
        <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-gradient-to-br from-[#6C63E8] to-[#312783] text-white shadow-lg shadow-black/30 ring-1 ring-white/15">
          <GiPerspectiveDiceSixFacesRandom size={18} />
        </span>
      )}
      <span className="min-w-0 leading-tight">
        <span className="block truncate text-[15px] font-extrabold text-white">{identity.site_name}</span>
        <span className="block text-[10.5px] font-semibold uppercase tracking-[0.18em] text-white/45">Operations</span>
      </span>
    </Link>
  );
}

function SidebarFooter() {
  const { user, logout } = useAuth();
  const { theme, toggleTheme } = useTheme();
  const router = useRouter();
  return (
    <div className="space-y-2 border-t border-white/10 pt-4">
      <div className="flex gap-1.5">
        <button
          onClick={toggleTheme}
          className="flex flex-1 items-center justify-center gap-2 rounded-xl bg-white/[0.06] px-3 py-2 text-xs font-semibold text-white/70 transition-colors hover:bg-white/10 hover:text-white"
        >
          {theme === 'dark' ? <BsSun size={12} /> : <BsMoonStars size={12} />}
          {theme === 'dark' ? 'Light' : 'Dark'}
        </button>
        <a
          href="/django-admin/"
          title="Raw database admin"
          className="flex items-center justify-center gap-2 rounded-xl bg-white/[0.06] px-3 py-2 text-xs font-semibold text-white/70 transition-colors hover:bg-white/10 hover:text-white"
        >
          <BsDatabase size={12} /> DB
        </a>
      </div>
      {user && (
        <div className="flex items-center gap-2.5 rounded-xl bg-white/[0.04] p-2.5">
          <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-[#6C63E8] to-[#312783] text-xs font-extrabold uppercase text-white">
            {user.username.slice(0, 2)}
          </span>
          <span className="min-w-0 flex-1 leading-tight">
            <span className="block truncate text-[13px] font-semibold text-white">{user.username}</span>
            <span className="block text-[10.5px] text-white/45">Staff</span>
          </span>
          <button
            onClick={async () => { await logout(); router.push('/login'); }}
            aria-label="Log out"
            title="Log out"
            className="rounded-lg p-2 text-white/55 transition-colors hover:bg-white/10 hover:text-white"
          >
            <BsBoxArrowRight size={14} />
          </button>
        </div>
      )}
    </div>
  );
}

const SHELL = 'bg-[radial-gradient(120%_60%_at_0%_0%,#2a2178_0%,#15104a_45%,#0b0826_100%)]';

/** Desktop: fixed rail. Mobile: a top bar with a drawer. */
export function Sidebar() {
  const [open, setOpen] = useState(false);
  const pathname = usePathname();
  useEffect(() => { setOpen(false); }, [pathname]);

  return (
    <>
      <aside className={cx('sticky top-0 hidden h-screen w-64 shrink-0 flex-col gap-6 overflow-y-auto border-r border-white/5 p-4 lg:flex', SHELL)}>
        <div className="px-1 pt-1"><Brand /></div>
        <NavLinks />
        <div className="mt-auto"><SidebarFooter /></div>
      </aside>

      <div className={cx('sticky top-0 z-40 flex items-center gap-3 border-b border-white/10 px-4 py-3 lg:hidden', SHELL)}>
        <button onClick={() => setOpen(true)} aria-label="Open menu" className="rounded-lg p-2 text-white hover:bg-white/10">
          <BsList size={20} />
        </button>
        <Brand />
        <BsActivity className="ml-auto text-white/40" size={16} />
      </div>
      {open && (
        <div className="fixed inset-0 z-50 bg-black/60 lg:hidden" onClick={() => setOpen(false)}>
          <aside
            className={cx('flex h-full w-72 flex-col gap-6 overflow-y-auto p-4', SHELL)}
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between px-1 pt-1">
              <Brand />
              <button onClick={() => setOpen(false)} aria-label="Close menu" className="rounded-lg p-2 text-white/70 hover:bg-white/10">
                <BsXLg size={14} />
              </button>
            </div>
            <NavLinks onNavigate={() => setOpen(false)} />
            <div className="mt-auto"><SidebarFooter /></div>
          </aside>
        </div>
      )}
    </>
  );
}

