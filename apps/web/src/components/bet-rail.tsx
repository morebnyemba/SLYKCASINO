'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { BsChevronDoubleRight, BsReceipt, BsTicketPerforated } from 'react-icons/bs';
import { SlipBody } from '@/components/betslip-panel';
import { useAuth } from '@/lib/auth-context';
import { useBetslip } from '@/lib/betslip-context';
import { useApi } from '@/lib/use-api';
import { useShell } from '@/lib/shell-context';

interface Bet {
  id: number;
  event: string;
  stake: string;
  odds: string;
  status: string;
  payout: string | null;
  placed_at: string;
}

interface Slip {
  id: number;
  stake: string;
  combined_odds: string;
  status: string;
  payout: string | null;
  placed_at: string;
  legs: { id: number; event: string }[];
}

const STATUS_STYLE: Record<string, string> = {
  open: 'bg-secondary/15 text-secondary',
  pending: 'bg-muted text-muted-foreground',
  won: 'bg-win/15 text-win',
  lost: 'bg-destructive/10 text-destructive',
  void: 'bg-muted text-muted-foreground',
};

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

function money(v: string | number) {
  return `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** Recent singles and multiples, open ones first. */
function MyBets() {
  const { user } = useAuth();
  const { status } = useBetslip();
  const { data: bets, refetch: refetchBets } = useApi<{ results?: Bet[] }>(user ? '/bets/?page_size=15' : null);
  const { data: slips, refetch: refetchSlips } = useApi<{ results?: Slip[] }>(user ? '/betslips/?page_size=10' : null);

  // Refresh after the slip places something.
  useEffect(() => {
    if (status && /placed/i.test(status)) { refetchBets(); refetchSlips(); }
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

  const rows = [
    ...(bets?.results ?? []).map((b) => ({
      key: `b${b.id}`, title: b.event, sub: `Single @ ${Number(b.odds).toFixed(2)}`,
      stake: b.stake, returns: b.status === 'won' ? b.payout : String(Number(b.stake) * Number(b.odds)),
      status: b.status, placed: b.placed_at,
    })),
    ...(slips?.results ?? []).map((s) => ({
      key: `s${s.id}`, title: `Multiple (${s.legs.length})`, sub: s.legs.map((l) => l.event.split(' — ')[0]).join(' · '),
      stake: s.stake, returns: s.status === 'won' ? s.payout : String(Number(s.stake) * Number(s.combined_odds)),
      status: s.status, placed: s.placed_at,
    })),
  ].sort((a, b) => {
    const ao = a.status === 'open' ? 0 : 1;
    const bo = b.status === 'open' ? 0 : 1;
    return ao - bo || new Date(b.placed).getTime() - new Date(a.placed).getTime();
  });

  if (rows.length === 0) {
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
        {rows.map((r) => (
          <li key={r.key} className="rounded-xl border border-border bg-background/50 p-3">
            <div className="flex items-start gap-2">
              <div className="min-w-0 flex-1">
                <p className="truncate text-[13px] font-bold">{r.title}</p>
                <p className="truncate text-[11px] text-muted-foreground">{r.sub}</p>
              </div>
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-extrabold uppercase ${STATUS_STYLE[r.status] ?? STATUS_STYLE.pending}`}>
                {r.status}
              </span>
            </div>
            <div className="mt-2 flex justify-between text-[11.5px]">
              <span className="text-muted-foreground">Stake <b className="text-foreground">{money(r.stake)}</b></span>
              <span className="text-muted-foreground">
                {r.status === 'won' ? 'Paid' : 'Returns'}{' '}
                <b className={r.status === 'lost' ? 'text-muted-foreground line-through' : 'text-win'}>{money(r.returns ?? 0)}</b>
              </span>
            </div>
          </li>
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
  const { legs, status } = useBetslip();
  const { setRailPref } = useShell();
  const [tab, setTab] = useState<'slip' | 'bets'>('slip');

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

  if (!open) return null;

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
        {tab === 'slip' ? <SlipBody variant="rail" /> : <MyBets />}
      </div>

    </aside>
  );
}
