'use client';

import { useState } from 'react';
import { BsTrash, BsXLg, BsReceipt } from 'react-icons/bs';
import { Card } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { Input } from '@slyk/ui/components/input';
import { useAuth } from '@/lib/auth-context';
import { useBetslip, type Selection } from '@/lib/betslip-context';

const SELECTION_LABEL: Record<Selection, string> = { home: '1', draw: 'X', away: '2' };

/** The slip body, shared by the desktop rail card and the mobile drawer. */
function SlipBody() {
  const { user } = useAuth();
  const {
    legs, stake, combinedOdds, potentialReturn, status, busy,
    removeLeg, clear, setStake, place,
  } = useBetslip();

  const isAcca = legs.length > 1;

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <p className="flex items-center gap-2 text-sm font-semibold">
          <BsReceipt size={15} /> Bet Slip
          <Badge variant="secondary">{legs.length}</Badge>
        </p>
        {legs.length > 0 && (
          <button onClick={clear} className="text-xs text-muted-foreground hover:text-foreground">
            Clear
          </button>
        )}
      </div>

      {legs.length === 0 ? (
        <p className="rounded-md bg-muted/50 px-3 py-6 text-center text-xs text-muted-foreground">
          Tap any odds to add a selection. Pick two or more for an accumulator.
        </p>
      ) : (
        <>
          <ul className="space-y-1.5">
            {legs.map((l) => (
              <li key={`${l.eventId}:${l.selection}`} className="flex items-center gap-2 rounded-md border border-border px-2.5 py-1.5">
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-medium">{l.eventName}</p>
                  <p className="text-[10px] text-muted-foreground">
                    {l.selection === 'home' ? 'Home' : l.selection === 'draw' ? 'Draw' : 'Away'} ({SELECTION_LABEL[l.selection]})
                  </p>
                </div>
                <span className="font-mono text-xs font-bold text-primary">{l.odds.toFixed(2)}</span>
                <button
                  onClick={() => removeLeg(l.eventId, l.selection)}
                  aria-label="Remove selection"
                  className="text-muted-foreground/60 transition-colors hover:text-red-500"
                >
                  <BsTrash size={12} />
                </button>
              </li>
            ))}
          </ul>

          {isAcca && (
            <div className="flex items-center justify-between rounded-md bg-primary/5 px-3 py-1.5 text-xs">
              <span className="text-muted-foreground">Accumulator ({legs.length} legs)</span>
              <span className="font-mono font-bold text-primary">{combinedOdds.toFixed(2)}</span>
            </div>
          )}

          <div className="space-y-1.5">
            <label className="text-xs text-muted-foreground">Stake</label>
            <Input value={stake} onChange={(e) => setStake(e.target.value)} inputMode="decimal" />
          </div>

          <div className="space-y-1 rounded-md border border-border px-3 py-2 text-sm">
            <div className="flex justify-between text-muted-foreground">
              <span>Total odds</span>
              <span className="font-mono">{combinedOdds.toFixed(2)}</span>
            </div>
            <div className="flex justify-between font-semibold">
              <span>Potential return</span>
              <span className="text-green-600">{potentialReturn.toFixed(2)}</span>
            </div>
          </div>

          {user ? (
            <button
              onClick={place}
              disabled={busy}
              className="w-full rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground transition-opacity hover:opacity-90 disabled:opacity-50"
            >
              {busy ? 'Placing…' : isAcca ? 'Place accumulator' : 'Place bet'}
            </button>
          ) : (
            <a
              href="/login"
              className="block w-full rounded-md bg-primary px-4 py-2 text-center text-sm font-medium text-primary-foreground hover:opacity-90"
            >
              Log in to bet
            </a>
          )}
          {status && <p className="text-xs text-muted-foreground">{status}</p>}
        </>
      )}
    </div>
  );
}

/** Desktop: a sticky card for the sportsbook right rail. */
export function BetslipCard() {
  return (
    <Card className="sticky top-20 p-4">
      <SlipBody />
    </Card>
  );
}

/** Mobile: a floating button + slide-up drawer, shown only when the slip is non-empty. */
export function BetslipDrawer() {
  const { legs } = useBetslip();
  const [open, setOpen] = useState(false);

  if (legs.length === 0) return null;

  return (
    <div className="lg:hidden">
      {!open && (
        <button
          onClick={() => setOpen(true)}
          className="fixed bottom-4 left-1/2 z-40 flex -translate-x-1/2 items-center gap-2 rounded-full bg-primary px-5 py-2.5 text-sm font-semibold text-primary-foreground shadow-lg"
        >
          <BsReceipt size={15} /> Bet Slip
          <span className="rounded-full bg-white/20 px-2 text-xs">{legs.length}</span>
        </button>
      )}
      {open && (
        <div className="fixed inset-0 z-50 flex items-end bg-black/40" onClick={() => setOpen(false)}>
          <div className="w-full rounded-t-2xl bg-background p-4" onClick={(e) => e.stopPropagation()}>
            <div className="mb-2 flex justify-end">
              <button onClick={() => setOpen(false)} aria-label="Close bet slip" className="text-muted-foreground">
                <BsXLg size={16} />
              </button>
            </div>
            <SlipBody />
          </div>
        </div>
      )}
    </div>
  );
}
