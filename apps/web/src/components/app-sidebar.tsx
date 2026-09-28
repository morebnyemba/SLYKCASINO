'use client';

import Link from 'next/link';
import { Suspense } from 'react';
import { usePathname, useSearchParams } from 'next/navigation';
import { BsLayoutSidebarInset, BsXLg } from 'react-icons/bs';
import {
  GiRollingDices, GiTrophy, GiRocketFlight, GiCherry, GiCardAceSpades,
  GiPokerHand, GiPodiumWinner, GiLightningFrequency, GiSoccerKick, GiCastle,
} from 'react-icons/gi';
import { FaGift, FaRegCommentDots, FaShieldAlt } from 'react-icons/fa';
import type { IconType } from 'react-icons';
import { SPORT_CATEGORIES } from '@/components/sports-sidebar';
import { ThemeToggle, SettingsMenu } from '@/components/settings-menu';
import { useShell } from '@/lib/shell-context';

interface NavItem {
  href: string;
  label: string;
  icon: IconType;
  live?: boolean;
}

const CASINO_ITEMS: NavItem[] = [
  { href: '/casino', label: 'Casino lobby', icon: GiCastle },
  { href: '/casino/crash', label: 'Aviator', icon: GiRocketFlight },
  { href: '/casino?category=slots', label: 'Slots', icon: GiCherry },
  { href: '/casino?category=live', label: 'Live casino', icon: GiPokerHand },
  { href: '/casino?category=table', label: 'Table games', icon: GiCardAceSpades },
  { href: '/casino?category=instant', label: 'Instant win', icon: GiLightningFrequency },
  { href: '/casino?category=virtual', label: 'Virtual sports', icon: GiSoccerKick },
];

const SPORTS_ITEMS: NavItem[] = [
  { href: '/sportsbook?tab=live', label: 'Live now', icon: GiTrophy, live: true },
  ...SPORT_CATEGORIES.map((s) => ({ href: `/sportsbook?sport=${s.id}`, label: s.label, icon: s.icon })),
];

const MORE_ITEMS: NavItem[] = [
  { href: '/promotions', label: 'Promotions', icon: FaGift },
  { href: '/tournaments', label: 'Tournaments', icon: GiPodiumWinner },
  { href: '/livechat', label: 'Live support', icon: FaRegCommentDots },
  { href: '/account/settings', label: 'Responsible gaming', icon: FaShieldAlt },
];

/** An item is active when its path matches and every query param it sets matches too. */
function isActive(href: string, pathname: string, query: URLSearchParams | null): boolean {
  const [path, qs] = href.split('?');
  if (path !== pathname) return false;
  const want = new URLSearchParams(qs ?? '');
  if (!qs) {
    // A bare section link (e.g. "/casino") is active only when no filter is applied.
    return !query || (!query.get('category') && !query.get('sport') && !query.get('tab'));
  }
  if (!query) return false;
  for (const [k, v] of want) if (query.get(k) !== v) return false;
  return true;
}

function Section({ title, items, compact, pathname, query, onNavigate }: {
  title: string;
  items: NavItem[];
  compact: boolean;
  pathname: string;
  query: URLSearchParams | null;
  onNavigate: () => void;
}) {
  return (
    <div className="py-2">
      {!compact && (
        <p className="px-3 pb-1.5 text-[10.5px] font-extrabold uppercase tracking-wider text-muted-foreground/70">{title}</p>
      )}
      <ul className="space-y-0.5">
        {items.map((item) => {
          const Icon = item.icon;
          const active = isActive(item.href, pathname, query);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                title={compact ? item.label : undefined}
                onClick={onNavigate}
                className={`group flex items-center gap-3 rounded-lg text-[13.5px] font-semibold transition-colors ${
                  compact ? 'h-10 justify-center' : 'px-3 py-2'
                } ${
                  active
                    ? 'bg-secondary/15 text-foreground shadow-[inset_3px_0_0_var(--secondary)]'
                    : 'text-muted-foreground hover:bg-muted/60 hover:text-foreground'
                }`}
              >
                <span className="relative flex w-5 shrink-0 justify-center">
                  <Icon size={17} className={active ? 'text-secondary' : ''} />
                  {item.live && <span className="absolute -right-0.5 -top-0.5 h-2 w-2 animate-pulse rounded-full bg-live" />}
                </span>
                {!compact && <span className="truncate">{item.label}</span>}
              </Link>
            </li>
          );
        })}
      </ul>
    </div>
  );
}

function SidebarNav({ query, variant }: { query: URLSearchParams | null; variant: 'rail' | 'drawer' }) {
  const pathname = usePathname();
  const { collapsed, toggleCollapsed, setMenuOpen } = useShell();
  const compact = variant === 'rail' && collapsed;
  const onSports = pathname.startsWith('/sportsbook');
  const sectionProps = { compact, pathname, query, onNavigate: () => setMenuOpen(false) };

  return (
    <div className="flex h-full flex-col">
      <div className={`flex items-center gap-2 border-b border-border ${compact ? 'h-16 justify-center' : 'h-16 px-3'}`}>
        {variant === 'rail' ? (
          <button
            onClick={toggleCollapsed}
            aria-label={collapsed ? 'Expand menu' : 'Collapse menu'}
            title={collapsed ? 'Expand menu' : 'Collapse menu'}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
          >
            <BsLayoutSidebarInset size={16} />
          </button>
        ) : (
          <button
            onClick={() => setMenuOpen(false)}
            aria-label="Close menu"
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-muted-foreground hover:bg-muted hover:text-foreground"
          >
            <BsXLg size={16} />
          </button>
        )}
        {!compact && (
          <div className="grid flex-1 grid-cols-2 gap-1 rounded-xl bg-muted/60 p-1 text-xs font-extrabold">
            <Link
              href="/casino"
              onClick={() => setMenuOpen(false)}
              className={`flex items-center justify-center gap-1.5 rounded-lg py-2 transition-colors ${
                !onSports ? 'bg-secondary text-white shadow' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <GiRollingDices size={14} /> Casino
            </Link>
            <Link
              href="/sportsbook"
              onClick={() => setMenuOpen(false)}
              className={`flex items-center justify-center gap-1.5 rounded-lg py-2 transition-colors ${
                onSports ? 'bg-secondary text-white shadow' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              <GiTrophy size={14} /> Sports
            </Link>
          </div>
        )}
      </div>

      <nav className="no-scrollbar flex-1 space-y-1 overflow-y-auto px-2 py-2">
        {onSports ? (
          <>
            <Section title="Sports" items={SPORTS_ITEMS} {...sectionProps} />
            <Section title="Casino" items={CASINO_ITEMS} {...sectionProps} />
          </>
        ) : (
          <>
            <Section title="Casino" items={CASINO_ITEMS} {...sectionProps} />
            <Section title="Sports" items={SPORTS_ITEMS} {...sectionProps} />
          </>
        )}
        <div className="mx-3 border-t border-border" />
        <Section title="More" items={MORE_ITEMS} {...sectionProps} />
      </nav>

      <div className={`flex items-center gap-1 border-t border-border p-2 ${compact ? 'flex-col' : ''}`}>
        <ThemeToggle className={compact ? '!w-9 !justify-center !px-0 [&>span]:hidden' : 'flex-1'} />
        <SettingsMenu placement="sidebar" />
      </div>
    </div>
  );
}

function SidebarWithParams({ variant }: { variant: 'rail' | 'drawer' }) {
  const query = useSearchParams();
  return <SidebarNav query={query} variant={variant} />;
}

function SidebarContent({ variant }: { variant: 'rail' | 'drawer' }) {
  // useSearchParams needs a Suspense boundary; the fallback renders the same nav
  // without query-aware highlighting so there's no layout shift.
  return (
    <Suspense fallback={<SidebarNav query={null} variant={variant} />}>
      <SidebarWithParams variant={variant} />
    </Suspense>
  );
}

/** Desktop left navigation rail (collapsible to icons). */
export function AppSidebar() {
  const { collapsed } = useShell();
  return (
    <aside
      className={`sticky top-0 hidden h-screen shrink-0 border-r border-border bg-sidebar text-sidebar-foreground transition-[width] duration-200 lg:block ${
        collapsed ? 'w-[68px]' : 'w-[244px]'
      }`}
    >
      <SidebarContent variant="rail" />
    </aside>
  );
}

/** Mobile slide-in navigation drawer, opened from the bottom nav's Menu tab. */
export function MobileMenu() {
  const { menuOpen, setMenuOpen } = useShell();
  if (!menuOpen) return null;
  return (
    <div className="fixed inset-0 z-[60] bg-black/60 lg:hidden" onClick={() => setMenuOpen(false)}>
      <aside
        className="animate-slyk-drawer h-full w-[82%] max-w-[300px] bg-sidebar text-sidebar-foreground shadow-2xl"
        onClick={(e) => e.stopPropagation()}
      >
        <SidebarContent variant="drawer" />
      </aside>
    </div>
  );
}
