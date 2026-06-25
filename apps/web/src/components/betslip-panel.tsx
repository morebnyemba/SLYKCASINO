'use client';

import { useState } from 'react';
import { BsXLg, BsReceipt, BsTicketPerforated } from 'react-icons/bs';
import { useAuth } from '@/lib/auth-context';
import { useBetslip, legKey, type Selection } from '@/lib/betslip-context';

const SELECTION_LABEL: Record<Selection, string> = { home: '1', draw: 'X', away: '2' };
const QUICK_STAKES = [5, 10, 25];

/** The slip body, shared by the desktop rail card and the mobile drawer. */
function SlipBody() {
  const { user } = useAuth();
  const {
    legs, mode, setMode, accaStake, setAccaStake, legStakes, setLegStake,
    combinedOdds, potentialPayout, status, busy,
    removeLeg, clear, place,
  } = useBetslip();

  const hasLegs = legs.length > 0;
  const isSingles = mode === 'singles';
  const isAcca = mode === 'acca' && hasLegs;

  const slipTabs: { id: 'acca' | 'singles'; label: string }[] = [
    { id: 'acca', label: legs.length > 1 ? 'Accumulator' : 'Single' },
    { id: 'singles', label: 'Singles' },
  ];

  let oddsLabel: string;
  let totalOdds: string;
  let placeLabel: string;
  if (isSingles) {
    const totalStake = legs.reduce((a, l) => a + (parseFloat(legStakes[legKey(l.eventId, l.selection)] || '0') || 0), 0);
    oddsLabel = `Total stake $${totalStake.toFixed(2)}`;
    totalOdds = `${legs.length} single${legs.length === 1 ? '' : 's'}`;
    placeLabel = `Place ${legs.length} bet${legs.length === 1 ? '' : 's'}`;
  } else {
    oddsLabel = legs.length > 1 ? 'Accumulator odds' : 'Odds';
    totalOdds = combinedOdds.toFixed(2);
    placeLabel = `Place bet · $${(parseFloat(accaStake || '0') || 0).toFixed(2)}`;
  }

  return (
    <div className="overflow-hidden rounded-2xl border border-border bg-card">
      <div className="flex items-center gap-2.5 border-b border-border bg-muted/40 px-4 py-3.5">
        <BsTicketPerforated size={15} className="text-foreground" />
        <span className="font-bold">Bet slip</span>
        <span className="flex h-[22px] min-w-[22px] items-center justify-center rounded-full bg-secondary px-1.5 text-xs font-extrabold text-white">
          {legs.length}
        </span>
        {hasLegs && (
          <button onClick={clear} className="ml-auto text-xs font-bold text-muted-foreground hover:text-foreground">
            Clear
          </button>
        )}
      </div>

      {hasLegs && (
        <div className="flex border-b border-border">
          {slipTabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setMode(t.id)}
              className={`flex-1 border-b-2 py-2.5 text-xs font-bold transition-colors ${
                mode === t.id
                  ? 'border-gold bg-muted/40 text-foreground'
                  : 'border-transparent text-muted-foreground hover:text-foreground'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}

      {!hasLegs && (
        <div className="px-5 py-9 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl bg-chip">
            <BsReceipt size={20} className="text-muted-foreground" />
          </div>
          <p className="mb-1 text-sm font-bold">Your bet slip is empty</p>
          <p className="text-xs leading-relaxed text-muted-foreground">
            Tap any odds to add a selection. Combine legs for an accumulator.
          </p>
        </div>
      )}

      {hasLegs && (
        <>
          <div className="max-h-[300px] overflow-y-auto">
            {legs.map((l) => {
              const key = legKey(l.eventId, l.selection);
              const stake = legStakes[key] || '';
              const stakeNum = parseFloat(stake) || 0;
              return (
                <div key={key} className="border-b border-border px-4 py-3">
                  <div className="flex items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="text-[13px] font-bold leading-tight">
                        {l.selection === 'home' ? 'Home' : l.selection === 'draw' ? 'Draw' : 'Away'} ({SELECTION_LABEL[l.selection]})
                      </p>
                      <p className="truncate text-[11px] text-muted-foreground">{l.eventName}</p>
                    </div>
                    <span className="font-mono text-sm font-bold text-gold">{l.odds.toFixed(2)}</span>
                    <button
                      onClick={() => removeLeg(l.eventId, l.selection)}
                      aria-label="Remove selection"
                      className="pl-0.5 text-muted-foreground transition-colors hover:text-destructive"
                    >
                      <BsXLg size={13} />
                    </button>
                  </div>
                  {isSingles && (
                    <div className="mt-2 flex items-center gap-2">
                      <div className="relative flex-1">
                        <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-xs text-muted-foreground">$</span>
                        <input
                          value={stake}
                          onChange={(e) => setLegStake(key, e.target.value)}
                          inputMode="decimal"
                          placeholder="0"
                          className="w-full rounded-md border border-border bg-muted/40 py-1.5 pl-5 pr-2 text-sm outline-none focus:ring-2 focus:ring-primary"
                        />
                      </div>
                      <span className="text-xs text-muted-foreground">→</span>
                      <span className="min-w-[58px] text-right text-[12.5px] font-bold tabular-nums text-win">
                        ${(stakeNum * l.odds).toFixed(2)}
                      </span>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="bg-muted/40 px-4 py-3.5">
            {isAcca && (
              <div className="mb-3">
                <p className="mb-1.5 text-xs font-bold text-muted-foreground">Total stake</p>
                <div className="relative">
                  <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-base font-bold text-muted-foreground">$</span>
                  <input
                    value={accaStake}
                    onChange={(e) => setAccaStake(e.target.value.replace(/[^0-9.]/g, ''))}
                    inputMode="decimal"
                    placeholder="0"
                    className="w-full rounded-lg border border-border bg-card py-2.5 pl-6 pr-3 text-base font-bold outline-none focus:ring-2 focus:ring-primary"
                  />
                </div>
                <div className="mt-2 flex gap-1.5">
                  {QUICK_STAKES.map((v) => (
                    <button
                      key={v}
                      onClick={() => setAccaStake(String(v))}
                      className="flex-1 rounded-md border border-border bg-chip py-1.5 text-xs font-bold text-muted-foreground hover:text-foreground"
                    >
                      ${v}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <div className="mb-1.5 flex items-center justify-between">
              <span className="text-[12.5px] text-muted-foreground">{oddsLabel}</span>
              <span className="font-mono text-sm font-bold">{totalOdds}</span>
            </div>
            <div className="mb-3.5 flex items-center justify-between">
              <span className="text-sm font-bold">Potential payout</span>
              <span className="text-lg font-extrabold text-win">${potentialPayout.toFixed(2)}</span>
            </div>

            {user ? (
              <button
                onClick={place}
                disabled={busy}
                className="w-full rounded-xl bg-gradient-to-br from-gold to-gold/70 px-4 py-3 text-sm font-extrabold text-[#1A1538] shadow-[0_6px_16px_rgba(0,0,0,0.3)] transition-opacity hover:opacity-90 disabled:opacity-50"
              >
                {busy ? 'Placing…' : placeLabel}
              </button>
            ) : (
              <a
                href="/login"
                className="block w-full rounded-xl bg-gradient-to-br from-gold to-gold/70 px-4 py-3 text-center text-sm font-extrabold text-[#1A1538] shadow-[0_6px_16px_rgba(0,0,0,0.3)] hover:opacity-90"
              >
                Log in to bet
              </a>
            )}
            {status && <p className="mt-2 text-xs text-muted-foreground">{status}</p>}
          </div>
        </>
      )}
    </div>
  );
}

/** Desktop: a sticky card for the sportsbook right rail. */
export function BetslipCard() {
  return (
    <div className="sticky top-20">
      <SlipBody />
    </div>
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
          className="fixed bottom-24 left-1/2 z-30 flex -translate-x-1/2 items-center gap-2 rounded-full bg-secondary px-5 py-2.5 text-sm font-semibold text-white shadow-lg"
        >
          <BsReceipt size={15} /> Bet Slip
          <span className="rounded-full bg-white/20 px-2 text-xs">{legs.length}</span>
        </button>
      )}
      {open && (
        <div className="fixed inset-0 z-50 flex items-end bg-black/40" onClick={() => setOpen(false)}>
          <div className="w-full p-4" onClick={(e) => e.stopPropagation()}>
            <div className="mb-2 flex justify-end">
              <button onClick={() => setOpen(false)} aria-label="Close bet slip" className="text-white">
                <BsXLg size={18} />
              </button>
            </div>
            <SlipBody />
          </div>
        </div>
      )}
    </div>
  );
}
