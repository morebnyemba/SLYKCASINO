'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { authedPost } from '@/lib/use-api';

export type Selection = 'home' | 'draw' | 'away';

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
  stake: string;
  combinedOdds: number;
  potentialReturn: number;
  status: string | null;
  busy: boolean;
  isOnSlip: (eventId: string | number, selection: Selection) => boolean;
  toggleLeg: (leg: BetLeg) => void;
  removeLeg: (eventId: string | number, selection: Selection) => void;
  clear: () => void;
  setStake: (s: string) => void;
  place: () => Promise<void>;
}

const BetslipContext = createContext<BetslipContextValue | null>(null);

export function BetslipProvider({ children }: { children: React.ReactNode }) {
  const { accessToken } = useAuth();
  const [legs, setLegs] = useState<BetLeg[]>([]);
  const [stake, setStake] = useState('10');
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

  const clear = useCallback(() => { setLegs([]); setStatus(null); }, []);

  const combinedOdds = useMemo(
    () => legs.reduce((acc, l) => acc * l.odds, 1),
    [legs],
  );
  const potentialReturn = useMemo(
    () => (parseFloat(stake || '0') || 0) * combinedOdds,
    [stake, combinedOdds],
  );

  const place = useCallback(async () => {
    if (!accessToken) { setStatus('Please log in to place a bet.'); return; }
    if (legs.length === 0) { setStatus('Add a selection first.'); return; }
    const stakeNum = Number(stake);
    if (!stakeNum || stakeNum <= 0) { setStatus('Enter a valid stake.'); return; }

    setBusy(true); setStatus('Placing…');
    const toLabel = (l: BetLeg) => `${l.eventName} — ${SELECTION_LABEL[l.selection]}`;

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
    setBusy(false);
  }, [accessToken, legs, stake]);

  const value: BetslipContextValue = {
    legs, stake, combinedOdds, potentialReturn, status, busy,
    isOnSlip, toggleLeg, removeLeg, clear, setStake, place,
  };
  return <BetslipContext.Provider value={value}>{children}</BetslipContext.Provider>;
}

export function useBetslip() {
  const ctx = useContext(BetslipContext);
  if (!ctx) throw new Error('useBetslip must be used within a BetslipProvider');
  return ctx;
}
