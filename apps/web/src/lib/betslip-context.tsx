'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { authedPost } from '@/lib/use-api';

export type Selection = 'home' | 'draw' | 'away';
export type SlipMode = 'acca' | 'singles';

/**
 * One pick on the slip: either a headline 1X2 price (`selection`) or an outcome of
 * a secondary market (`outcomeId`, with its market name and outcome label).
 */
export interface BetLeg {
  eventId: string | number;
  eventName: string;
  selection: Selection;
  odds: number;
  outcomeId?: number;
  /** Secondary markets only: e.g. "Total goals 2.5". */
  marketName?: string;
  /** Secondary markets only: e.g. "Over 2.5". */
  outcomeLabel?: string;
  /** Market identity used so a new pick in the same market replaces the old one. */
  marketId?: number;
}

const SELECTION_LABEL: Record<Selection, string> = { home: 'Home', draw: 'Draw', away: 'Away' };
const STORAGE_KEY = 'slyk:betslip';

function legKey(eventId: string | number, selection: Selection | string, outcomeId?: number) {
  return outcomeId != null ? `o:${outcomeId}` : `${eventId}:${selection}`;
}

function keyOf(leg: BetLeg) {
  return legKey(leg.eventId, leg.selection, leg.outcomeId);
}

/** Legs in the same market (1X2, or one secondary market) are mutually exclusive. */
function sameMarket(a: BetLeg, b: BetLeg) {
  if (String(a.eventId) !== String(b.eventId)) return false;
  if (a.outcomeId == null && b.outcomeId == null) return true; // both 1X2
  return a.marketId != null && a.marketId === b.marketId;
}

/** Label sent to the API and shown in bet history. */
function betLabel(l: BetLeg) {
  const pick = l.outcomeId != null ? `${l.marketName}: ${l.outcomeLabel}` : SELECTION_LABEL[l.selection];
  return `${l.eventName} — ${pick}`.slice(0, 200);
}

function legPayload(l: BetLeg) {
  return l.outcomeId != null
    ? { event: betLabel(l), outcome_id: l.outcomeId, odds: l.odds }
    : { event: betLabel(l), event_id: Number(l.eventId), selection: l.selection, odds: l.odds };
}

interface BetslipContextValue {
  legs: BetLeg[];
  mode: SlipMode;
  setMode: (m: SlipMode) => void;
  accaStake: string;
  setAccaStake: (s: string) => void;
  legStakes: Record<string, string>;
  setLegStake: (key: string, value: string) => void;
  combinedOdds: number;
  potentialPayout: number;
  status: string | null;
  busy: boolean;
  /** Event ids with more than one pick — those can't be combined in a multiple. */
  conflictingEvents: Set<string>;
  isOnSlip: (eventId: string | number, selection: Selection) => boolean;
  isOutcomeOnSlip: (outcomeId: number) => boolean;
  toggleLeg: (leg: BetLeg) => void;
  removeLeg: (key: string) => void;
  clear: () => void;
  place: () => Promise<void>;
  /** Mobile bet-slip sheet visibility, shared so the bottom nav can open it. */
  slipOpen: boolean;
  setSlipOpen: (open: boolean) => void;
}

const BetslipContext = createContext<BetslipContextValue | null>(null);

export function BetslipProvider({ children }: { children: React.ReactNode }) {
  const { accessToken } = useAuth();
  const [legs, setLegs] = useState<BetLeg[]>([]);
  const [mode, setMode] = useState<SlipMode>('acca');
  const [accaStake, setAccaStake] = useState('10');
  const [legStakes, setLegStakes] = useState<Record<string, string>>({});
  const [status, setStatus] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [slipOpen, setSlipOpen] = useState(false);

  // Restore a slip the player was building before navigating/refreshing.
  useEffect(() => {
    try {
      const raw = window.localStorage.getItem(STORAGE_KEY);
      if (raw) setLegs(JSON.parse(raw));
    } catch {
      /* ignore malformed slip */
    }
  }, []);

  useEffect(() => {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(legs));
    } catch {
      /* storage may be unavailable */
    }
  }, [legs]);

  const keys = useMemo(() => new Set(legs.map(keyOf)), [legs]);

  const isOnSlip = useCallback(
    (eventId: string | number, selection: Selection) => keys.has(legKey(eventId, selection)),
    [keys],
  );
  const isOutcomeOnSlip = useCallback((outcomeId: number) => keys.has(legKey('', '', outcomeId)), [keys]);

  const toggleLeg = useCallback((leg: BetLeg) => {
    setStatus(null);
    setLegs((prev) => {
      const key = keyOf(leg);
      if (prev.some((l) => keyOf(l) === key)) return prev.filter((l) => keyOf(l) !== key);
      // One pick per market: tapping another price in the same market swaps it.
      return [...prev.filter((l) => !sameMarket(l, leg)), leg];
    });
  }, []);

  const removeLeg = useCallback((key: string) => {
    setLegs((prev) => prev.filter((l) => keyOf(l) !== key));
  }, []);

  const clear = useCallback(() => { setLegs([]); setLegStakes({}); setStatus(null); }, []);

  const setLegStake = useCallback((key: string, value: string) => {
    setLegStakes((prev) => ({ ...prev, [key]: value.replace(/[^0-9.]/g, '') }));
  }, []);

  const conflictingEvents = useMemo(() => {
    const seen = new Set<string>();
    const dupes = new Set<string>();
    for (const l of legs) {
      const id = String(l.eventId);
      if (seen.has(id)) dupes.add(id);
      seen.add(id);
    }
    return dupes;
  }, [legs]);

  const combinedOdds = useMemo(() => legs.reduce((acc, l) => acc * l.odds, 1), [legs]);

  const potentialPayout = useMemo(() => {
    if (mode === 'singles') {
      return legs.reduce((acc, l) => {
        const stake = parseFloat(legStakes[keyOf(l)] || '0') || 0;
        return acc + stake * l.odds;
      }, 0);
    }
    return (parseFloat(accaStake || '0') || 0) * combinedOdds;
  }, [mode, legs, legStakes, accaStake, combinedOdds]);

  /** On a 409 odds_changed, move the leg to the new price so the player can re-confirm. */
  const applyPriceChange = useCallback((leg: BetLeg, body?: Record<string, unknown>) => {
    const next = body && body.code === 'odds_changed' ? Number(body.odds) : NaN;
    if (!Number.isFinite(next)) return false;
    setLegs((prev) => prev.map((l) => (keyOf(l) === keyOf(leg) ? { ...l, odds: next } : l)));
    return true;
  }, []);

  const place = useCallback(async () => {
    if (!accessToken) { setStatus('Please log in to place a bet.'); return; }
    if (legs.length === 0) { setStatus('Add a selection first.'); return; }

    setBusy(true); setStatus('Placing…');

    if (mode === 'singles') {
      const placeable = legs.filter((l) => (parseFloat(legStakes[keyOf(l)] || '0') || 0) > 0);
      if (placeable.length === 0) { setStatus('Enter a stake for at least one selection.'); setBusy(false); return; }
      const results = await Promise.all(placeable.map((l) => authedPost('/bets/', {
        ...legPayload(l), stake: parseFloat(legStakes[keyOf(l)] || '0'),
      }, accessToken)));
      const failed = results.filter((r) => r.error);
      const repriced = placeable.filter((l, i) => applyPriceChange(l, results[i].body)).length;
      const placedKeys = new Set(placeable.filter((_, i) => !results[i].error).map(keyOf));
      if (placedKeys.size > 0) {
        setLegs((prev) => prev.filter((l) => !placedKeys.has(keyOf(l))));
        setLegStakes((prev) => Object.fromEntries(Object.entries(prev).filter(([k]) => !placedKeys.has(k))));
      }
      if (failed.length === 0) setStatus(placeable.length === 1 ? 'Bet placed.' : 'Bets placed.');
      else if (repriced > 0) setStatus(`Odds changed on ${repriced} selection${repriced === 1 ? '' : 's'} — check the new prices and place again.`);
      else if (failed.length === results.length) setStatus(`Rejected: ${failed[0].error}`);
      else setStatus(`Placed ${results.length - failed.length}/${results.length} bets. Rejected: ${failed[0].error}`);
    } else {
      const stakeNum = Number(accaStake);
      if (!stakeNum || stakeNum <= 0) { setStatus('Enter a valid stake.'); setBusy(false); return; }
      if (conflictingEvents.size > 0) {
        setStatus('Multiples can’t combine two picks from the same match — remove one or switch to Singles.');
        setBusy(false);
        return;
      }
      const res = legs.length === 1
        ? await authedPost('/bets/', { ...legPayload(legs[0]), stake: stakeNum }, accessToken)
        : await authedPost('/betslips/', { stake: stakeNum, legs: legs.map(legPayload) }, accessToken);
      if (res.error) {
        // The API names the first stale outcome; move that leg to its new price.
        const staleId = res.body?.outcome_id;
        const stale = res.body?.code === 'odds_changed'
          ? legs.find((l) => l.outcomeId != null && l.outcomeId === staleId) ?? (legs.length === 1 ? legs[0] : undefined)
          : undefined;
        if (stale && applyPriceChange(stale, res.body)) setStatus('Odds changed — check the new price and place again.');
        else setStatus(`Rejected: ${res.error}`);
      } else {
        setStatus(legs.length === 1 ? 'Bet placed.' : 'Multiple placed.');
        setLegs([]);
      }
    }
    setBusy(false);
  }, [accessToken, legs, mode, legStakes, accaStake, conflictingEvents, applyPriceChange]);

  const value: BetslipContextValue = {
    legs, mode, setMode, accaStake, setAccaStake, legStakes, setLegStake,
    combinedOdds, potentialPayout, status, busy, conflictingEvents,
    isOnSlip, isOutcomeOnSlip, toggleLeg, removeLeg, clear, place,
    slipOpen, setSlipOpen,
  };
  return <BetslipContext.Provider value={value}>{children}</BetslipContext.Provider>;
}

export function useBetslip() {
  const ctx = useContext(BetslipContext);
  if (!ctx) throw new Error('useBetslip must be used within a BetslipProvider');
  return ctx;
}

export { legKey, keyOf };
