'use client';

import { BetSlip } from '@/components/bet-slip';
import { useLiveOdds, type LiveOdds } from '@/lib/use-live-odds';
import type { Selection } from '@/lib/betslip-context';

/**
 * Wraps the bet slip on an event page so its price tracks the realtime odds
 * channel. The active price follows the chosen outcome (1/X/2).
 */
export function LiveBetSlip({ eventId, label, selection, initial }: {
  eventId: string | number;
  label: string;
  selection: Selection;
  initial: LiveOdds;
}) {
  const live = useLiveOdds(eventId, initial);
  const active =
    selection === 'draw' ? live.odds_draw
    : selection === 'away' ? live.odds_away
    : live.odds;
  const odds = active != null ? active : (initial.odds ?? 1.95);

  return (
    <div className="space-y-2">
      {live.live && (
        <p className="flex items-center gap-1.5 text-xs font-medium text-green-600">
          <span className="h-1.5 w-1.5 rounded-full bg-green-600 animate-pulse" />
          Live odds
        </p>
      )}
      <BetSlip event={label} initialOdds={odds} eventId={eventId} selection={selection} />
    </div>
  );
}
