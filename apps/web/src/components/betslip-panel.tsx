'use client';

import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { useEffect } from 'react';
import { BsLockFill, BsXLg, BsReceipt, BsTrash3 } from 'react-icons/bs';
import { useAuth } from '@/lib/auth-context';
import { useBetslip, keyOf, type BetLeg, type Selection } from '@/lib/betslip-context';
import { formatOdds, useSettings } from '@/lib/settings-context';
import { Spinner } from '@slyk/ui/components/spinner';

const SELECTION_CODE: Record<Selection, string> = { home: '1', draw: 'X', away: '2' };
const QUICK_STAKES = [5, 10, 25, 50, 100];

/** "Arsenal" / "Draw" / "Chelsea" — the pick in plain words, from the "A v B" event name. */
function pickLabel(leg: BetLeg): string {
  if (leg.outcomeId != null) return leg.outcomeLabel ?? 'Selection';
  if (leg.selection === 'draw') return 'Draw';
  const [home, away] = leg.eventName.split(/\s+(?:v|vs\.?)\s+/i);
  if (leg.selection === 'away') return away ?? 'Away';
  return away ? home : leg.eventName;
}

function money(n: number) {
  return `$${n.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** The slip body, shared by the desktop rail card and the mobile sheet. */
export function SlipBody({ onClose, variant = 'card' }: {
  onClose?: () => void;
  /** `rail` renders flat and full-height for the desktop right column (which has its own header). */
  variant?: 'card' | 'rail';
}) {
  const { user } = useAuth();
  const { oddsFormat } = useSettings();
  const {
    legs, mode, setMode, accaStake, setAccaStake, legStakes, setLegStake,
    combinedOdds, potentialPayout, status, busy,
    removeLeg, clear, place, conflictingEvents, hasPriceChanges, hasSuspended, acceptPriceChanges,
  } = useBetslip();

  const hasLegs = legs.length > 0;
  const isSingles = mode === 'singles';
  const fmt = (o: number) => formatOdds(o, oddsFormat);

  const slipTabs: { id: 'acca' | 'singles'; label: string }[] = [
    { id: 'acca', label: legs.length > 1 ? `Multiple (${legs.length})` : 'Single' },
    { id: 'singles', label: 'Singles' },
  ];

  const totalStake = isSingles
    ? legs.reduce((a, l) => a + (parseFloat(legStakes[keyOf(l)] || '0') || 0), 0)
    : parseFloat(accaStake || '0') || 0;
  const placeLabel = isSingles
    ? `Place ${legs.length} bet${legs.length === 1 ? '' : 's'} · ${money(totalStake)}`
    : `Place bet · ${money(totalStake)}`;
  const rejected = !!status && /^(Rejected|Enter|Please|Odds changed|Multiples|Placed \d)/.test(status);

  return (
    <div className={variant === 'rail'
      ? 'flex h-full min-h-0 flex-col'
      : 'flex max-h-full flex-col overflow-hidden rounded-2xl border border-border bg-card'}
    >
      <div className={`flex items-center gap-2.5 px-4 py-3 ${variant === 'rail' && !hasLegs ? 'hidden' : ''}`}>
        <BsReceipt size={16} className={variant === 'rail' ? 'hidden' : 'text-secondary'} />
        <span className={`font-extrabold ${variant === 'rail' ? 'text-sm text-muted-foreground' : ''}`}>
          {variant === 'rail' ? `${legs.length} selection${legs.length === 1 ? '' : 's'}` : 'Bet slip'}
        </span>
        {hasLegs && variant !== 'rail' && (
          <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-secondary px-1.5 text-[11px] font-extrabold text-white">
            {legs.length}
          </span>
        )}
        <div className="ml-auto flex items-center gap-1">
          {hasLegs && (
            <button
              onClick={clear}
              className="flex items-center gap-1.5 rounded-md px-2 py-1 text-xs font-bold text-muted-foreground transition-colors hover:bg-muted hover:text-foreground"
            >
              <BsTrash3 size={11} /> Clear
            </button>
          )}
          {onClose && (
            <button onClick={onClose} aria-label="Close bet slip" className="rounded-md p-1.5 text-muted-foreground hover:bg-muted hover:text-foreground">
              <BsXLg size={15} />
            </button>
          )}
        </div>
      </div>

      {hasLegs && (
        <div className="mx-3 mb-2 grid grid-cols-2 gap-1 rounded-xl bg-muted/60 p-1">
          {slipTabs.map((t) => (
            <button
              key={t.id}
              onClick={() => setMode(t.id)}
              className={`rounded-lg py-1.5 text-xs font-bold transition-colors ${
                mode === t.id ? 'bg-card text-foreground shadow' : 'text-muted-foreground hover:text-foreground'
              }`}
            >
              {t.label}
            </button>
          ))}
        </div>
      )}

      {!hasLegs && (
        <div className={`px-6 pb-8 pt-4 text-center ${variant === 'rail' ? 'my-auto' : ''}`}>
          <div className="mx-auto mb-3 flex h-14 w-14 items-center justify-center rounded-2xl bg-muted">
            <BsReceipt size={22} className="text-muted-foreground" />
          </div>
          <p className="mb-1 text-sm font-bold">Your bet slip is empty</p>
          <p className="mb-4 text-xs leading-relaxed text-muted-foreground">
            Tap any price to add a selection. Add two or more for a multiple.
          </p>
          {user && (
            <Link href="/account/bets" onClick={onClose} className="text-xs font-bold text-secondary hover:underline">
              View my bets →
            </Link>
          )}
        </div>
      )}

      {hasLegs && (
        <>
          <div className="min-h-0 flex-1 space-y-2 overflow-y-auto px-3 pb-3">
            {legs.map((l) => {
              const key = keyOf(l);
              const conflict = !isSingles && conflictingEvents.has(String(l.eventId));
              const stake = legStakes[key] || '';
              const stakeNum = parseFloat(stake) || 0;
              return (
                <div key={key} className={`rounded-xl border bg-background/50 p-3 ${conflict ? 'border-gold' : 'border-border'}`}>
                  <div className="flex items-start gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="truncate text-[13px] font-extrabold leading-tight">{pickLabel(l)}</p>
                      <p className="mt-0.5 text-[11px] font-semibold text-muted-foreground">
                        {l.outcomeId != null ? l.marketName : `Match result · ${SELECTION_CODE[l.selection]}`}
                      </p>
                      <p className="mt-0.5 truncate text-[11px] text-muted-foreground">{l.eventName}</p>
                      {conflict && (
                        <p className="mt-1 text-[11px] font-semibold text-gold">Same match as another pick — place as Singles</p>
                      )}
                    </div>
                    {l.suspended ? (
                      <span className="flex items-center gap-1 rounded-md bg-muted px-2 py-1 text-[11px] font-extrabold uppercase text-muted-foreground">
                        <BsLockFill size={9} /> Suspended
                      </span>
                    ) : (
                      <span className="flex flex-col items-end">
                        {l.changedFrom != null && (
                          <span className="text-[10.5px] font-semibold tabular-nums text-muted-foreground line-through">{fmt(l.changedFrom)}</span>
                        )}
                        <span className={`rounded-md px-2 py-1 text-sm font-extrabold tabular-nums ${
                          l.changedFrom == null ? 'bg-odds'
                            : l.odds > l.changedFrom ? 'bg-win/15 text-win' : 'bg-destructive/10 text-destructive'
                        }`}>
                          {l.changedFrom != null && (l.odds > l.changedFrom ? '▲ ' : '▼ ')}{fmt(l.odds)}
                        </span>
                      </span>
                    )}
                    <button
                      onClick={() => removeLeg(key)}
                      aria-label="Remove selection"
                      className="rounded-md p-1 text-muted-foreground transition-colors hover:bg-muted hover:text-destructive"
                    >
                      <BsXLg size={12} />
                    </button>
                  </div>
                  {isSingles && (
                    <div className="mt-2.5 flex items-center gap-2">
                      <div className="relative flex-1">
                        <span className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-xs font-bold text-muted-foreground">$</span>
                        <input
                          value={stake}
                          onChange={(e) => setLegStake(key, e.target.value)}
                          inputMode="decimal"
                          placeholder="Stake"
                          aria-label={`Stake for ${pickLabel(l)}`}
                          className="w-full rounded-lg border border-border bg-input py-2 pl-6 pr-2 text-sm font-bold outline-none focus:ring-2 focus:ring-ring"
                        />
                      </div>
                      <div className="min-w-[80px] text-right">
                        <p className="text-[10px] font-semibold text-muted-foreground">Returns</p>
                        <p className="text-[13px] font-extrabold tabular-nums text-win">{money(stakeNum * l.odds)}</p>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="border-t border-border bg-muted/30 px-4 py-3.5">
            {!isSingles && (
              <div className="mb-3">
                <div className="relative">
                  <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-sm font-bold text-muted-foreground">Stake $</span>
                  <input
                    value={accaStake}
                    onChange={(e) => setAccaStake(e.target.value.replace(/[^0-9.]/g, ''))}
                    inputMode="decimal"
                    placeholder="0.00"
                    aria-label="Stake"
                    className="w-full rounded-xl border border-border bg-input py-2.5 pl-[4.5rem] pr-3 text-right text-base font-extrabold tabular-nums outline-none focus:ring-2 focus:ring-ring"
                  />
                </div>
                <div className="mt-2 grid grid-cols-5 gap-1.5">
                  {QUICK_STAKES.map((v) => (
                    <button
                      key={v}
                      onClick={() => setAccaStake(String(v))}
                      className={`rounded-lg border py-1.5 text-xs font-bold transition-colors ${
                        accaStake === String(v)
                          ? 'border-secondary bg-secondary/15 text-foreground'
                          : 'border-border bg-card text-muted-foreground hover:text-foreground'
                      }`}
                    >
                      {v}
                    </button>
                  ))}
                </div>
              </div>
            )}

            <dl className="mb-3 space-y-1 text-[12.5px]">
              {!isSingles && (
                <div className="flex justify-between">
                  <dt className="text-muted-foreground">{legs.length > 1 ? 'Total odds' : 'Odds'}</dt>
                  <dd className="font-bold tabular-nums">{fmt(combinedOdds)}</dd>
                </div>
              )}
              <div className="flex justify-between">
                <dt className="text-muted-foreground">Total stake</dt>
                <dd className="font-bold tabular-nums">{money(totalStake)}</dd>
              </div>
              <div className="flex items-baseline justify-between pt-1">
                <dt className="text-sm font-bold">Potential win</dt>
                <dd className="text-lg font-extrabold tabular-nums text-win">{money(potentialPayout)}</dd>
              </div>
            </dl>

            {user ? (
              hasSuspended ? (
                <button
                  disabled
                  className="w-full rounded-xl bg-muted px-4 py-3 text-sm font-extrabold text-muted-foreground"
                >
                  Remove suspended selections
                </button>
              ) : hasPriceChanges ? (
                <button
                  onClick={acceptPriceChanges}
                  className="w-full rounded-xl bg-gold px-4 py-3 text-sm font-extrabold text-gold-foreground shadow-lg transition-opacity hover:opacity-90"
                >
                  Accept odds changes
                </button>
              ) : (
                <button
                  onClick={place}
                  disabled={busy}
                  className="w-full rounded-xl bg-win px-4 py-3 text-sm font-extrabold text-win-foreground shadow-lg transition-opacity hover:opacity-90 disabled:opacity-50"
                >
                  {busy ? <span className="inline-flex items-center justify-center gap-2"><Spinner size={14} />Placing…</span> : placeLabel}
                </button>
              )
            ) : (
              <Link
                href="/login"
                onClick={onClose}
                className="block w-full rounded-xl bg-win px-4 py-3 text-center text-sm font-extrabold text-win-foreground shadow-lg hover:opacity-90"
              >
                Log in to place bet
              </Link>
            )}
            {status && (
              <p className={`mt-2 rounded-lg px-3 py-2 text-xs font-semibold ${
                rejected ? 'bg-destructive/10 text-destructive' : 'bg-win/10 text-win'
              }`}>
                {status}
              </p>
            )}
          </div>
        </>
      )}
      {!hasLegs && status && (
        <p className="mx-4 mb-4 rounded-lg bg-win/10 px-3 py-2 text-center text-xs font-semibold text-win">{status}</p>
      )}
    </div>
  );
}

/**
 * Mobile: a slide-up sheet opened from the bottom nav, plus a floating summary bar
 * on sportsbook pages whenever the slip has selections. Mounted once in the root layout.
 */
export function BetslipDrawer() {
  const { legs, combinedOdds, slipOpen, setSlipOpen } = useBetslip();
  const { oddsFormat } = useSettings();
  const pathname = usePathname();

  // Close the sheet on navigation so it never lingers over a new page.
  useEffect(() => { setSlipOpen(false); }, [pathname, setSlipOpen]);

  return (
    <div className="xl:hidden">
      {!slipOpen && legs.length > 0 && pathname.startsWith('/sportsbook') && (
        <button
          onClick={() => setSlipOpen(true)}
          className="fixed bottom-[76px] left-3 right-3 z-30 flex lg:bottom-5 lg:left-auto lg:right-5 lg:w-80 items-center gap-3 rounded-2xl bg-win px-4 py-3 text-win-foreground shadow-[0_10px_30px_rgba(0,0,0,0.45)]"
        >
          <span className="flex h-6 min-w-6 items-center justify-center rounded-full bg-win-foreground px-1.5 text-xs font-extrabold text-win">
            {legs.length}
          </span>
          <span className="text-sm font-extrabold">Bet slip</span>
          <span className="ml-auto text-[13px] font-bold tabular-nums">Odds {formatOdds(combinedOdds, oddsFormat)}</span>
        </button>
      )}
      {slipOpen && (
        <div className="fixed inset-0 z-50 flex items-end bg-black/60 lg:items-stretch lg:justify-end" onClick={() => setSlipOpen(false)}>
          <div
            className="animate-slyk-sheet flex max-h-[85vh] w-full flex-col rounded-t-3xl lg:max-h-none lg:w-[380px] lg:rounded-none lg:pt-4 bg-background p-2 pb-[max(env(safe-area-inset-bottom),0.5rem)] shadow-[0_-10px_40px_rgba(0,0,0,0.5)]"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex justify-center pb-2 pt-1 lg:hidden">
              <span className="h-[5px] w-10 rounded-full bg-border" />
            </div>
            <SlipBody onClose={() => setSlipOpen(false)} />
          </div>
        </div>
      )}
    </div>
  );
}
