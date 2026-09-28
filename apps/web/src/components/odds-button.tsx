'use client';

import { useEffect, useRef, useState } from 'react';
import { BsLockFill } from 'react-icons/bs';
import { useBetslip, type Selection } from '@/lib/betslip-context';
import { formatOdds, useSettings } from '@/lib/settings-context';

/**
 * A tappable price that adds/removes a selection on the shared bet slip. Honours
 * the player's odds-format preference and flashes green/red when the price moves.
 */
export function OddsButton({
  eventId, eventName, selection = 'home', odds, label, move, size = 'md', disabled = false, className = '', outcome,
  stackOnMobile = false,
}: {
  eventId: string | number;
  eventName: string;
  /** 1X2 pick. Ignored when `outcome` is given. */
  selection?: Selection;
  /** A secondary-market outcome to back instead of a 1X2 price. */
  outcome?: { id: number; marketId: number; marketName: string; label: string };
  odds: number | string | null | undefined;
  /** Small caption shown above the price ("1", "X", "Draw"…). */
  label?: string;
  /** Last known movement, e.g. from `previous_odds`. */
  move?: 'up' | 'down';
  size?: 'sm' | 'md' | 'lg';
  /** Put the caption above the price on phones (narrow 3-column rows). */
  stackOnMobile?: boolean;
  disabled?: boolean;
  className?: string;
}) {
  const { isOnSlip, isOutcomeOnSlip, toggleLeg } = useBetslip();
  const { oddsFormat } = useSettings();
  const price = odds != null ? Number(odds) : NaN;
  const available = !disabled && Number.isFinite(price) && price > 1;
  const active = available && (outcome ? isOutcomeOnSlip(outcome.id) : isOnSlip(eventId, selection));

  // Flash when the price changes while mounted (live odds on the event page).
  const prev = useRef(price);
  const [flash, setFlash] = useState<'up' | 'down' | null>(null);
  useEffect(() => {
    if (Number.isFinite(prev.current) && Number.isFinite(price) && price !== prev.current) {
      setFlash(price > prev.current ? 'up' : 'down');
      const t = setTimeout(() => setFlash(null), 1600);
      prev.current = price;
      return () => clearTimeout(t);
    }
    prev.current = price;
  }, [price]);

  const shownMove = flash ?? move;
  const sizing = size === 'lg' ? 'h-14 px-3 text-base' : size === 'sm' ? 'min-h-11 px-3 py-2 text-[13.5px]' : 'h-11 px-2 text-[13.5px]';

  if (!available) {
    // Suspended/closed: keep the caption so the market still reads, with a lock instead of a price.
    return (
      <span
        className={`flex items-center rounded-lg bg-odds/50 text-muted-foreground/60 ${
          label ? (stackOnMobile ? 'flex-col justify-center gap-0.5 sm:flex-row sm:justify-between' : 'justify-between gap-2') : 'justify-center'
        } ${sizing} ${className}`}
        aria-label={label ? `${label}: price unavailable` : 'Price unavailable'}
      >
        {label && <span className="max-w-full truncate text-[11px] font-bold">{label}</span>}
        {Number.isFinite(price) ? <BsLockFill size={11} /> : '—'}
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={() => toggleLeg(
        outcome
          ? {
            eventId, eventName, selection: 'home', odds: price, outcomeId: outcome.id,
            marketId: outcome.marketId, marketName: outcome.marketName, outcomeLabel: outcome.label,
          }
          : { eventId, eventName, selection, odds: price },
      )}
      aria-pressed={active}
      className={`relative flex items-center rounded-lg font-extrabold tabular-nums transition-colors ${
        !label ? 'justify-center'
          : stackOnMobile ? 'flex-col justify-center gap-0.5 py-1.5 sm:flex-row sm:justify-between sm:gap-2 sm:py-2'
            : 'justify-between gap-2'
      } ${sizing} ${
        active
          ? 'bg-secondary text-white shadow-[0_4px_14px_color-mix(in_srgb,var(--secondary)_45%,transparent)]'
          : 'bg-odds text-foreground hover:bg-odds-hover'
      } ${flash === 'up' ? 'animate-flash-up' : flash === 'down' ? 'animate-flash-down' : ''} ${className}`}
    >
      {label && (
        <span className={`max-w-full text-[11px] font-bold ${
          stackOnMobile ? 'line-clamp-2 text-center leading-tight sm:line-clamp-none sm:truncate sm:text-left' : 'truncate'
        } ${active ? 'text-white/75' : 'text-muted-foreground'}`}>{label}</span>
      )}
      <span className="flex items-center gap-1">
        {shownMove && (
          <span className={`text-[8px] ${active ? 'text-white/80' : shownMove === 'up' ? 'text-win' : 'text-down'}`}>
            {shownMove === 'up' ? '▲' : '▼'}
          </span>
        )}
        {formatOdds(price, oddsFormat)}
      </span>
    </button>
  );
}
