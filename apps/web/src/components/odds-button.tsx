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
  eventId, eventName, selection, odds, label, move, size = 'md', disabled = false, className = '',
}: {
  eventId: string | number;
  eventName: string;
  selection: Selection;
  odds: number | string | null | undefined;
  /** Small caption shown above the price ("1", "X", "Draw"…). */
  label?: string;
  /** Last known movement, e.g. from `previous_odds`. */
  move?: 'up' | 'down';
  size?: 'md' | 'lg';
  disabled?: boolean;
  className?: string;
}) {
  const { isOnSlip, toggleLeg } = useBetslip();
  const { oddsFormat } = useSettings();
  const price = odds != null ? Number(odds) : NaN;
  const available = !disabled && Number.isFinite(price) && price > 1;
  const active = available && isOnSlip(eventId, selection);

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
  const sizing = size === 'lg' ? 'h-14 px-3 text-base' : 'h-11 px-2 text-[13.5px]';

  if (!available) {
    return (
      <span
        className={`flex items-center justify-center rounded-lg bg-odds/50 text-muted-foreground/60 ${sizing} ${className}`}
        aria-label="Price unavailable"
      >
        {Number.isFinite(price) ? <BsLockFill size={11} /> : '—'}
      </span>
    );
  }

  return (
    <button
      type="button"
      onClick={() => toggleLeg({ eventId, eventName, selection, odds: price })}
      aria-pressed={active}
      className={`relative flex items-center rounded-lg font-extrabold tabular-nums transition-colors ${
        label ? 'justify-between gap-2' : 'justify-center'
      } ${sizing} ${
        active
          ? 'bg-secondary text-white shadow-[0_4px_14px_color-mix(in_srgb,var(--secondary)_45%,transparent)]'
          : 'bg-odds text-foreground hover:bg-odds-hover'
      } ${flash === 'up' ? 'animate-flash-up' : flash === 'down' ? 'animate-flash-down' : ''} ${className}`}
    >
      {label && (
        <span className={`truncate text-[11px] font-bold ${active ? 'text-white/75' : 'text-muted-foreground'}`}>{label}</span>
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
