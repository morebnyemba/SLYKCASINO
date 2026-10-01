'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect, useRef, useState } from 'react';
import { BsChevronDoubleRight, BsReceipt, BsTicketPerforated } from 'react-icons/bs';
import { SlipBody } from '@/components/betslip-panel';
import { BetTicket, sortTickets, ticketFromBet, ticketFromSlip, type ApiBet, type ApiSlip } from '@/components/bet-ticket';
import { useAuth } from '@/lib/auth-context';
import { isAuthRoute } from '@/lib/auth-routes';
import { useBetslip } from '@/lib/betslip-context';
import { useApi } from '@/lib/use-api';
import { useShell } from '@/lib/shell-context';
import { LoadingState } from '@slyk/ui/components/spinner';

/**
 * Whether the desktop rail is showing: the player's explicit choice (header
 * button / hide), else only while the slip has picks — it slides in with the
 * first selection and gets out of the way once the slip is empty.
 */
export function useRailOpen() {
  const { legs } = useBetslip();
  const { railPref } = useShell();
  return railPref ?? legs.length > 0;
}

/** Recent singles and multiples, open ones first. */
function MyBets() {
  const { user } = useAuth();
  const { status } = useBetslip();
  const { data: bets, error: betsError, loading: betsLoading, refetch: refetchBets } =
    useApi<{ results?: ApiBet[] }>(user ? '/bets/?page_size=15' : null);
  const { data: slips, error: slipsError, loading: slipsLoading, refetch: refetchSlips } =
    useApi<{ results?: ApiSlip[] }>(user ? '/betslips/?page_size=10' : null);

  // Refresh after the slip places something (and when in-play bets resolve).
  useEffect(() => {
    if (status && /placed|in-play/i.test(status)) { refetchBets(); refetchSlips(); }
  }, [status, refetchBets, refetchSlips]);

  if (!user) {
    return (
      <div className="my-auto px-6 text-center">
        <p className="mb-1 text-sm font-bold">Track your bets here</p>
        <p className="mb-4 text-xs text-muted-foreground">Log in to see open and settled bets.</p>
        <Link href="/login" className="rounded-lg bg-win px-4 py-2 text-xs font-extrabold text-win-foreground">Log in</Link>
      </div>
    );
  }

  const rows = sortTickets([
    ...(bets?.results ?? []).map(ticketFromBet),
    ...(slips?.results ?? []).map(ticketFromSlip),
  ]);

  // A failed request must not read as "no bets" (or a partial list as complete).
  if (betsError || slipsError) {
    return (
      <div className="my-auto px-6 text-center">
        <p className="mb-1 text-sm font-bold">Couldn’t load your bets</p>
        <p className="mb-4 text-xs text-muted-foreground">Check your connection and try again.</p>
        <button
          onClick={() => { if (betsError) refetchBets(); if (slipsError) refetchSlips(); }}
          className="rounded-lg bg-secondary px-4 py-2 text-xs font-extrabold text-white"
        >
          Retry
        </button>
      </div>
    );
  }

  if (rows.length === 0) {
    if (betsLoading || slipsLoading) {
      return <LoadingState className="my-auto" label="Loading your bets…" />;
    }
    return (
      <div className="my-auto px-6 text-center">
        <p className="mb-1 text-sm font-bold">No bets yet</p>
        <p className="text-xs text-muted-foreground">Bets you place will show up here.</p>
      </div>
    );
  }

  return (
    <div className="min-h-0 flex-1 overflow-y-auto">
      <ul className="space-y-2 p-3">
        {rows.map((t) => (
          <li key={t.key}><BetTicket ticket={t} compact /></li>
        ))}
      </ul>
      <Link href="/account/bets" className="block pb-4 text-center text-xs font-bold text-secondary hover:underline">
        Full bet history →
      </Link>
    </div>
  );
}

/**
 * Desktop right column (xl+): bet slip and my bets, full height under the header,
 * mirroring the left nav rail. Below xl the slip is a drawer instead.
 */
export function BetRail() {
  const open = useRailOpen();
  const { user } = useAuth();
  const { legs, status } = useBetslip();
  const { setRailPref } = useShell();
  const [tab, setTab] = useState<'slip' | 'bets'>('slip');
  const onAuthPage = isAuthRoute(usePathname());

  // A new pick always brings the slip tab forward, and the first pick re-opens the
  // rail even if the player hid it earlier. An emptied slip hands control back to
  // the default (hidden).
  const prevCount = useRef(legs.length);
  useEffect(() => {
    if (legs.length > 0) setTab('slip');
    if (prevCount.current === 0 && legs.length > 0) setRailPref(null);
    if (prevCount.current > 0 && legs.length === 0) {
      if (status && /placed/i.test(status)) {
        // Emptied by placing a bet: stay open and show it under My bets.
        setRailPref(true);
        setTab('bets');
      } else {
        setRailPref(null);
      }
    }
    prevCount.current = legs.length;
  }, [legs.length, status, setRailPref]);

  if (!open || onAuthPage) return null;

  const tabClass = (active: boolean) =>
    `relative flex h-full flex-1 items-center justify-center gap-2 text-sm font-extrabold transition-colors ${
      active ? 'text-foreground' : 'text-muted-foreground hover:text-foreground'
    }`;

  return (
    <aside
      aria-label="Bet slip"
      className="sticky top-[var(--header-h)] hidden h-[calc(100dvh-var(--header-h))] w-[340px] shrink-0 flex-col border-l border-border bg-sidebar xl:flex"
    >
      <div className="flex h-12 shrink-0 items-stretch border-b border-border">
        <button onClick={() => setTab('slip')} className={tabClass(tab === 'slip')}>
          <BsReceipt size={14} /> Bet slip
          {legs.length > 0 && (
            <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-secondary px-1.5 text-[11px] text-white">
              {legs.length}
            </span>
          )}
          {tab === 'slip' && <span className="absolute inset-x-6 bottom-0 h-[3px] rounded-t-full bg-secondary" />}
        </button>
        <button onClick={() => setTab('bets')} className={tabClass(tab === 'bets')}>
          <BsTicketPerforated size={14} /> My bets
          {tab === 'bets' && <span className="absolute inset-x-6 bottom-0 h-[3px] rounded-t-full bg-secondary" />}
        </button>
        <button
          onClick={() => setRailPref(false)}
          aria-label="Hide bet slip"
          title="Hide bet slip"
          className="flex w-11 shrink-0 items-center justify-center border-l border-border text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
        >
          <BsChevronDoubleRight size={13} />
        </button>
      </div>

      <div className="flex min-h-0 flex-1 flex-col">
        {/* Keyed by account so a logout/login never shows the previous player's bets. */}
        {tab === 'slip' ? <SlipBody variant="rail" /> : <MyBets key={user?.userId ?? 'logged-out'} />}
      </div>

    </aside>
  );
}
