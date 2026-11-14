'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { BsHouseDoor, BsReceipt, BsTicketPerforated } from 'react-icons/bs';
import { GiCardRandom, GiTrophy } from 'react-icons/gi';
import type { IconType } from 'react-icons';
import { useAuth } from '@/lib/auth-context';
import { useBetslip } from '@/lib/betslip-context';

const tabClass = 'relative flex flex-1 flex-col items-center gap-0.5 py-0.5 text-[10px] font-bold transition-colors active:scale-95';

function TabLink({ href, label, icon: Icon, active }: { href: string; label: string; icon: IconType; active: boolean }) {
  return (
    <Link href={href} aria-current={active ? 'page' : undefined} className={`${tabClass} ${active ? 'text-secondary' : 'text-muted-foreground'}`}>
      <span className={`flex h-7 w-12 items-center justify-center rounded-full transition-colors ${active ? 'bg-secondary/20' : ''}`}>
        <Icon size={19} />
      </span>
      <span>{label}</span>
    </Link>
  );
}

/** "Add selections for up to 10% bonus", then how far the slip is from the next tier. */
function BonusStrip() {
  const { legs, bonus, maxBonusPercent, setSlipOpen } = useBetslip();
  if (maxBonusPercent <= 0) return null;
  let text: string;
  if (legs.length === 0) text = `Add selections for up to ${maxBonusPercent}% multi-bet bonus`;
  else if (bonus.next) {
    const more = bonus.next.minLegs - bonus.qualifying;
    text = `Add ${more} more selection${more === 1 ? '' : 's'} (odds ${bonus.minOdds.toFixed(2)}+) for ${bonus.next.percent}% bonus`;
  } else text = `${maxBonusPercent}% multi-bet bonus unlocked`;
  return (
    <button
      onClick={() => legs.length > 0 && setSlipOpen(true)}
      className="block w-full bg-gold px-2 pb-4 pt-1 text-center text-[11px] font-bold leading-tight text-gold-foreground"
    >
      {text}
    </button>
  );
}

/**
 * Mobile-only tab bar: Home, Sports, the bet slip (raised in the middle, with its
 * count), Casino and My bets, under a multi-bet bonus strip. The menu drawer and
 * search are in the header. Desktop uses the sidebar + header.
 */
export function BottomNav() {
  const pathname = usePathname();
  const { user } = useAuth();
  const { legs, slipOpen, setSlipOpen } = useBetslip();

  return (
    <div className="fixed inset-x-0 bottom-0 z-40 lg:hidden">
      <BonusStrip />
      <nav className="flex items-end border-t border-border bg-sidebar/95 px-1 pb-[max(env(safe-area-inset-bottom),0.5rem)] pt-1.5 shadow-[0_-8px_24px_rgba(0,0,0,0.12)] backdrop-blur-xl">
        <TabLink href="/home" label="Home" icon={BsHouseDoor} active={pathname === '/home'} />
        <TabLink href="/sportsbook" label="Sports" icon={GiTrophy} active={pathname.startsWith('/sportsbook')} />
        <button
          onClick={() => setSlipOpen(!slipOpen)}
          aria-label={`Bet slip${legs.length ? `, ${legs.length} selection${legs.length === 1 ? '' : 's'}` : ''}`}
          className={`${tabClass} ${slipOpen ? 'text-secondary' : 'text-foreground'}`}
        >
          {/* Raised centre button, like a betting-shop slip. */}
          <span className={`relative -mt-5 flex h-14 w-14 items-center justify-center rounded-full border-4 border-background shadow-lg transition-colors ${
            legs.length ? 'bg-secondary text-secondary-foreground' : 'bg-foreground text-background'
          }`}>
            <BsReceipt size={22} />
            {legs.length > 0 && (
              <span className="absolute -right-1 -top-1 flex h-5 min-w-5 items-center justify-center rounded-full bg-win px-1 text-[11px] font-extrabold text-win-foreground">
                {legs.length}
              </span>
            )}
          </span>
          <span>Bet slip</span>
        </button>
        <TabLink href="/casino" label="Casino" icon={GiCardRandom} active={pathname.startsWith('/casino') || pathname.startsWith('/aviator')} />
        <TabLink
          href={user ? '/account/bets' : '/login'}
          label="My bets"
          icon={BsTicketPerforated}
          active={pathname.startsWith('/account/bets')}
        />
      </nav>
    </div>
  );
}
