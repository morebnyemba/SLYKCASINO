'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { authedPost } from '@/lib/use-api';

export type Selection = 'home' | 'draw' | 'away';
export type SlipMode = 'acca' | 'singles';

export interface BetLeg {
  eventId: string | number;
  eventName: string;
  selection: Selection;
  odds: number;
}

const SELECTION_LABEL: Record<Selection, string> = { home: 'Home', draw: 'Draw', away: 'Away' };
const STORAGE_KEY = 'slyk:betslip';

function legKey(eventId: string | number, selection: Selection) {
  return `${eventId}:${selection}`;
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
  isOnSlip: (eventId: string | number, selection: Selection) => boolean;
  toggleLeg: (leg: BetLeg) => void;
  removeLeg: (eventId: string | number, selection: Selection) => void;
  clear: () => void;
  place: () => Promise<void>;
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

  const isOnSlip = useCallback(
    (eventId: string | number, selection: Selection) =>
      legs.some((l) => legKey(l.eventId, l.selection) === legKey(eventId, selection)),
    [legs],
  );

  const toggleLeg = useCallback((leg: BetLeg) => {
    setStatus(null);
    setLegs((prev) => {
      const key = legKey(leg.eventId, leg.selection);
      // One selection per event: drop any other pick on the same event first.
      const withoutEvent = prev.filter((l) => String(l.eventId) !== String(leg.eventId));
      const alreadyExact = prev.some((l) => legKey(l.eventId, l.selection) === key);
      return alreadyExact ? withoutEvent : [...withoutEvent, leg];
    });
  }, []);

  const removeLeg = useCallback((eventId: string | number, selection: Selection) => {
    setLegs((prev) => prev.filter((l) => legKey(l.eventId, l.selection) !== legKey(eventId, selection)));
  }, []);

  const clear = useCallback(() => { setLegs([]); setLegStakes({}); setStatus(null); }, []);

  const setLegStake = useCallback((key: string, value: string) => {
    setLegStakes((prev) => ({ ...prev, [key]: value.replace(/[^0-9.]/g, '') }));
  }, []);

  const combinedOdds = useMemo(
    () => legs.reduce((acc, l) => acc * l.odds, 1),
    [legs],
  );

  const potentialPayout = useMemo(() => {
    if (mode === 'singles') {
      return legs.reduce((acc, l) => {
        const stake = parseFloat(legStakes[legKey(l.eventId, l.selection)] || '0') || 0;
        return acc + stake * l.odds;
      }, 0);
    }
    return (parseFloat(accaStake || '0') || 0) * combinedOdds;
  }, [mode, legs, legStakes, accaStake, combinedOdds]);

  const place = useCallback(async () => {
    if (!accessToken) { setStatus('Please log in to place a bet.'); return; }
    if (legs.length === 0) { setStatus('Add a selection first.'); return; }
    const toLabel = (l: BetLeg) => `${l.eventName} — ${SELECTION_LABEL[l.selection]}`;

    setBusy(true); setStatus('Placing…');

    if (mode === 'singles') {
      const placeable = legs.filter((l) => (parseFloat(legStakes[legKey(l.eventId, l.selection)] || '0') || 0) > 0);
      if (placeable.length === 0) { setStatus('Enter a stake for at least one selection.'); setBusy(false); return; }
      const results = await Promise.all(placeable.map((l) => authedPost('/bets/', {
        event: toLabel(l), event_id: Number(l.eventId), selection: l.selection,
        odds: l.odds, stake: parseFloat(legStakes[legKey(l.eventId, l.selection)] || '0'),
      }, accessToken)));
      const failed = results.filter((r) => r.error);
      if (failed.length === results.length) {
        setStatus(`Rejected: ${failed[0].error}`);
      } else {
        setStatus(failed.length > 0 ? `Placed ${results.length - failed.length}/${results.length} bets.` : 'Bets placed.');
        const placedKeys = new Set(placeable.map((l) => legKey(l.eventId, l.selection)));
        setLegs((prev) => prev.filter((l) => !placedKeys.has(legKey(l.eventId, l.selection))));
        setLegStakes({});
      }
    } else {
      const stakeNum = Number(accaStake);
      if (!stakeNum || stakeNum <= 0) { setStatus('Enter a valid stake.'); setBusy(false); return; }
      let error: string | undefined;
      if (legs.length === 1) {
        const l = legs[0];
        ({ error } = await authedPost('/bets/', {
          event: toLabel(l), event_id: Number(l.eventId), selection: l.selection,
          odds: l.odds, stake: stakeNum,
        }, accessToken));
      } else {
        ({ error } = await authedPost('/betslips/', {
          stake: stakeNum,
          legs: legs.map((l) => ({
            event: toLabel(l), event_id: Number(l.eventId), selection: l.selection, odds: l.odds,
          })),
        }, accessToken));
      }
      if (error) {
        setStatus(`Rejected: ${error}`);
      } else {
        setStatus(legs.length === 1 ? 'Bet placed.' : 'Accumulator placed.');
        setLegs([]);
      }
    }
    setBusy(false);
  }, [accessToken, legs, mode, legStakes, accaStake]);

  const value: BetslipContextValue = {
    legs, mode, setMode, accaStake, setAccaStake, legStakes, setLegStake,
    combinedOdds, potentialPayout, status, busy,
    isOnSlip, toggleLeg, removeLeg, clear, place,
  };
  return <BetslipContext.Provider value={value}>{children}</BetslipContext.Provider>;
}

export function useBetslip() {
  const ctx = useContext(BetslipContext);
  if (!ctx) throw new Error('useBetslip must be used within a BetslipProvider');
  return ctx;
}

export { legKey };
