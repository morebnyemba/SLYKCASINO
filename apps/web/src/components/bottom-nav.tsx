'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BsList, BsTicketPerforated, BsReceipt } from 'react-icons/bs';
import { GiTrophy, GiRollingDices } from 'react-icons/gi';
import type { IconType } from 'react-icons';
import { useAuth } from '@/lib/auth-context';
import { useBetslip } from '@/lib/betslip-context';
import { useShell } from '@/lib/shell-context';

const tabClass = 'relative flex flex-1 flex-col items-center gap-1 py-1 text-[10px] font-bold transition-colors';

function TabLink({ href, label, icon: Icon, active }: { href: string; label: string; icon: IconType; active: boolean }) {
  return (
    <Link href={href} className={`${tabClass} ${active ? 'text-secondary' : 'text-muted-foreground'}`}>
      {active && <span className="absolute -top-2 h-[3px] w-8 rounded-b-full bg-secondary" />}
      <Icon size={20} />
      <span>{label}</span>
    </Link>
  );
}

/** Mobile-only tab bar: menu drawer, products, bet slip and bets. Desktop uses the sidebar + header. */
export function BottomNav() {
  const pathname = usePathname();
  const { user } = useAuth();
  const { legs, slipOpen, setSlipOpen } = useBetslip();
  const { menuOpen, setMenuOpen } = useShell();

  return (
    <nav className="fixed inset-x-0 bottom-0 z-40 flex border-t border-border bg-sidebar/95 px-1 pb-[max(env(safe-area-inset-bottom),0.75rem)] pt-2 backdrop-blur-md lg:hidden">
      <button
        onClick={() => setMenuOpen(!menuOpen)}
        className={`${tabClass} ${menuOpen ? 'text-secondary' : 'text-muted-foreground'}`}
      >
        <BsList size={21} />
        <span>Menu</span>
      </button>
      <TabLink href="/casino" label="Casino" icon={GiRollingDices} active={pathname.startsWith('/casino')} />
      <TabLink href="/sportsbook" label="Sports" icon={GiTrophy} active={pathname.startsWith('/sportsbook')} />
      <button
        onClick={() => setSlipOpen(!slipOpen)}
        className={`${tabClass} ${slipOpen ? 'text-secondary' : 'text-muted-foreground'}`}
      >
        <span className="relative">
          <BsReceipt size={20} />
          {legs.length > 0 && (
            <span className="absolute -right-2.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-win px-1 text-[10px] font-extrabold text-win-foreground">
              {legs.length}
            </span>
          )}
        </span>
        <span>Bet slip</span>
      </button>
      <TabLink
        href={user ? '/account/bets' : '/login'}
        label="My bets"
        icon={BsTicketPerforated}
        active={pathname.startsWith('/account/bets')}
      />
    </nav>
  );
}
