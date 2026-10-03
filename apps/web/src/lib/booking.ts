import { config } from '@/lib/config';
import type { BetLeg, Selection } from '@/lib/betslip-context';

/** A booked pick as the API returns it: re-priced, with whether it can still be backed. */
interface BookedLeg {
  event_id: number;
  event_name: string;
  selection: Selection;
  outcome_id: number | null;
  market_id: number | null;
  market_name: string | null;
  outcome_label: string | null;
  odds: string | null;
  available: boolean;
}

export interface Booking {
  code: string;
  legs: BookedLeg[];
  available: number;
}

/** Strip spaces and upper-case, as the API does. */
export function normaliseCode(raw: string) {
  return raw.replace(/\s+/g, '').toUpperCase();
}

/** Book the slip's picks under a short code (guests may book too). */
export async function createBooking(legs: BetLeg[], token?: string | null): Promise<{ code?: string; error?: string }> {
  const selections = legs.map((l) => (l.outcomeId != null
    ? { outcome_id: l.outcomeId }
    : { event_id: Number(l.eventId), selection: l.selection }));
  try {
    const res = await fetch(`${config.apiUrl}/booking-codes/`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', ...(token ? { Authorization: `Bearer ${token}` } : {}) },
      body: JSON.stringify({ selections }),
    });
    const json = (await res.json().catch(() => ({}))) as { code?: string; detail?: string };
    return res.ok ? { code: json.code } : { error: json.detail ?? 'Could not book this slip.' };
  } catch {
    return { error: 'Network error — try again.' };
  }
}

/**
 * Load a booking code as bet-slip legs. Picks that can no longer be backed
 * (finished, suspended, no price) are left out and counted in `skipped`.
 */
export async function loadBooking(raw: string): Promise<{ legs?: BetLeg[]; skipped?: number; error?: string }> {
  const code = normaliseCode(raw);
  if (!code) return { error: 'Enter a booking code.' };
  try {
    const res = await fetch(`${config.apiUrl}/booking-codes/${encodeURIComponent(code)}/`, { cache: 'no-store' });
    if (res.status === 404) return { error: `No slip found for code ${code}.` };
    if (!res.ok) return { error: 'Could not load that code — try again.' };
    const booking = (await res.json()) as Booking;
    const legs: BetLeg[] = booking.legs
      .filter((l) => l.available && l.odds != null)
      .map((l) => ({
        eventId: l.event_id,
        eventName: l.event_name,
        selection: l.selection,
        odds: Number(l.odds),
        ...(l.outcome_id != null ? {
          outcomeId: l.outcome_id,
          marketId: l.market_id ?? undefined,
          marketName: l.market_name ?? undefined,
          outcomeLabel: l.outcome_label ?? undefined,
        } : {}),
      }));
    return { legs, skipped: booking.legs.length - legs.length };
  } catch {
    return { error: 'Network error — try again.' };
  }
}

/** Link that opens the sportsbook with this code loaded onto the slip. */
export function bookingLink(code: string) {
  const origin = typeof window !== 'undefined' ? window.location.origin : '';
  return `${origin}/sportsbook?code=${encodeURIComponent(code)}`;
}
