'use client';

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { config } from '@/lib/config';
import { onBoardFrame } from '@/lib/live-board';
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
  /** Live: the price the player last saw, while a newer price awaits their OK. */
  changedFrom?: number;
  /** Live: this pick can't be backed right now (market suspended / betting closed). */
  suspended?: boolean;
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

/**
 * In-play bets come back ACCEPTING: the stake is held while the server re-checks
 * price, suspension and score after a short delay. Poll each until it resolves
 * (open = accepted, rejected = refunded). Unresolved after ~45s counts as pending.
 */
async function awaitAcceptance(
  paths: string[], token: string, signal: AbortSignal,
): Promise<{ accepted: number; rejected: number; pending: number }> {
  const outcome = { accepted: 0, rejected: 0, pending: 0 };
  const pause = () => new Promise<void>((resolve) => {
    const id = setTimeout(resolve, 2000);
    signal.addEventListener('abort', () => { clearTimeout(id); resolve(); }, { once: true });
  });
  await Promise.all(paths.map(async (path) => {
    for (let i = 0; i < 22 && !signal.aborted; i++) {
      await pause();
      if (signal.aborted) return;
      try {
        const res = await fetch(`${config.apiUrl}${path}`, { headers: { Authorization: `Bearer ${token}` }, cache: 'no-store', signal });
        if (!res.ok) continue;
        const { status } = (await res.json()) as { status?: string };
        if (status === 'accepting') continue;
        if (status === 'rejected') outcome.rejected++; else outcome.accepted++;
        return;
      } catch { /* retry */ }
    }
    outcome.pending++;
  }));
  return outcome;
}

function acceptanceMessage({ accepted, rejected, pending }: { accepted: number; rejected: number; pending: number }) {
  if (rejected === 0 && pending === 0) return accepted === 1 ? 'In-play bet accepted.' : 'In-play bets accepted.';
  if (accepted === 0 && pending === 0) {
    return `In-play bet${rejected === 1 ? '' : 's'} not accepted — the price or score changed. Stake refunded.`;
  }
  const parts = [accepted && `${accepted} accepted`, rejected && `${rejected} not accepted (refunded)`, pending && `${pending} still confirming`];
  return `In-play bets: ${parts.filter(Boolean).join(', ')}.`;
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
  /** Some picks moved price since the player saw them (they must accept first). */
  hasPriceChanges: boolean;
  /** Some picks are suspended and can't be placed right now. */
  hasSuspended: boolean;
  acceptPriceChanges: () => void;
  /** Mobile bet-slip sheet visibility, shared so the bottom nav can open it. */
  slipOpen: boolean;
  setSlipOpen: (open: boolean) => void;
}

const BetslipContext = createContext<BetslipContextValue | null>(null);

export function BetslipProvider({ children }: { children: React.ReactNode }) {
  const { accessToken } = useAuth();
  // In-play acceptance polling belongs to the session that placed the bet: stop
  // it on logout/account switch or unmount so it never reports into another.
  const pollRef = useRef<AbortController | null>(null);
  useEffect(() => {
    const ctrl = new AbortController();
    pollRef.current = ctrl;
    return () => ctrl.abort();
  }, [accessToken]);
  const confirmInPlay = useCallback(async (paths: string[], token: string) => {
    const ctrl = pollRef.current;
    if (!ctrl) return;
    const result = await awaitAcceptance(paths, token, ctrl.signal);
    if (!ctrl.signal.aborted) setStatus(acceptanceMessage(result));
  }, []);
  const [legs, setLegs] = useState<BetLeg[]>([]);
  const legsRef = useRef(legs);
  legsRef.current = legs;
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

  // Live prices: re-read every pick's current price and availability every 5s,
  // and straight away when the board says one of the slip's matches changed.
  const legSignature = legs.map(keyOf).join('|');
  useEffect(() => {
    if (!legSignature) return;
    const current = legsRef.current;
    const eventIds = [...new Set(current.filter((l) => l.outcomeId == null).map((l) => String(l.eventId)))];
    const outcomeIds = current.filter((l) => l.outcomeId != null).map((l) => String(l.outcomeId));
    const watched = new Set(current.map((l) => String(l.eventId)));
    const query = `/events/prices/?events=${eventIds.join(',')}&outcomes=${outcomeIds.join(',')}`;
    let cancelled = false;
    let pending: ReturnType<typeof setTimeout> | undefined;

    async function refresh() {
      if (document.visibilityState === 'hidden') return;
      try {
        const res = await fetch(`${config.apiUrl}${query}`, { cache: 'no-store' });
        if (!res.ok || cancelled) return;
        const data = (await res.json()) as {
          events: Record<string, { odds: string; odds_draw: string | null; odds_away: string | null; main_open: boolean }>;
          outcomes: Record<string, { odds: string; open: boolean }>;
        };
        if (cancelled) return;
        setLegs((prev) => {
          let changed = false;
          const next = prev.map((l) => {
            let price: number | null = null;
            let open = false;
            if (l.outcomeId != null) {
              const o = data.outcomes[String(l.outcomeId)];
              if (o) { price = Number(o.odds); open = o.open; }
            } else {
              const e = data.events[String(l.eventId)];
              if (e) {
                const raw = l.selection === 'home' ? e.odds : l.selection === 'draw' ? e.odds_draw : e.odds_away;
                price = raw != null ? Number(raw) : null;
                open = e.main_open && price != null;
              }
            }
            if (price == null || !Number.isFinite(price)) {
              if (l.suspended) return l;
              changed = true;
              return { ...l, suspended: true };
            }
            const seen = l.changedFrom ?? l.odds;
            const moved = price !== l.odds;
            if (!moved && l.suspended === !open) return l;
            changed = true;
            return {
              ...l,
              odds: price,
              suspended: !open,
              // Flag a move against what the player last accepted; moving back clears it.
              changedFrom: price === seen ? undefined : seen,
            };
          });
          return changed ? next : prev;
        });
      } catch { /* offline: keep the last prices */ }
    }

    void refresh();
    const interval = setInterval(refresh, 5000);
    const off = onBoardFrame((frame) => {
      if (!watched.has(String(frame.event_id))) return;
      clearTimeout(pending);
      pending = setTimeout(refresh, 250);
    });
    return () => { cancelled = true; clearInterval(interval); clearTimeout(pending); off(); };
  }, [legSignature]);

  const hasPriceChanges = legs.some((l) => l.changedFrom != null);
  const hasSuspended = legs.some((l) => l.suspended);
  const acceptPriceChanges = useCallback(() => {
    setLegs((prev) => prev.map((l) => (l.changedFrom != null ? { ...l, changedFrom: undefined } : l)));
    setStatus(null);
  }, []);

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
    setLegs((prev) => prev.map((l) => (keyOf(l) === keyOf(leg)
      ? { ...l, odds: next, changedFrom: next === (l.changedFrom ?? l.odds) ? undefined : (l.changedFrom ?? l.odds) }
      : l)));
    return true;
  }, []);

  const place = useCallback(async () => {
    if (!accessToken) { setStatus('Please log in to place a bet.'); return; }
    if (legs.length === 0) { setStatus('Add a selection first.'); return; }
    if (legs.some((l) => l.suspended)) { setStatus('Remove suspended selections to place your bet.'); return; }
    if (legs.some((l) => l.changedFrom != null)) { setStatus('Odds changed — accept the new prices to continue.'); return; }

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
      const accepting = results
        .map((r) => r.data as { id?: number; status?: string } | undefined)
        .filter((d): d is { id: number; status: string } => d?.status === 'accepting' && d.id != null)
        .map((d) => `/bets/${d.id}/`);
      if (failed.length === 0) {
        setStatus(accepting.length > 0
          ? 'Bet placed — confirming in-play price…'
          : placeable.length === 1 ? 'Bet placed.' : 'Bets placed.');
      } else if (repriced > 0) setStatus(`Odds changed on ${repriced} selection${repriced === 1 ? '' : 's'} — check the new prices and place again.`);
      else if (failed.length === results.length) setStatus(`Rejected: ${failed[0].error}`);
      else setStatus(`Placed ${results.length - failed.length}/${results.length} bets. Rejected: ${failed[0].error}`);
      if (accepting.length > 0) {
        setBusy(false);
        await confirmInPlay(accepting, accessToken);
        return;
      }
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
          ? legs.find((l) => (staleId != null
            ? l.outcomeId === staleId
            // A 1X2 pick has no outcome row: the API names its event and selection.
            : l.outcomeId == null && String(l.eventId) === String(res.body?.event_id) && l.selection === res.body?.selection))
            ?? (legs.length === 1 ? legs[0] : undefined)
          : undefined;
        if (stale && applyPriceChange(stale, res.body)) setStatus('Odds changed — check the new price and place again.');
        else setStatus(`Rejected: ${res.error}`);
      } else {
        const placed = res.data as { id?: number; status?: string } | undefined;
        const inPlay = placed?.status === 'accepting' && placed.id != null;
        setStatus(inPlay
          ? `${legs.length === 1 ? 'Bet' : 'Multiple'} placed — confirming in-play price…`
          : legs.length === 1 ? 'Bet placed.' : 'Multiple placed.');
        setLegs([]);
        if (inPlay) {
          setBusy(false);
          const path = legs.length === 1 ? `/bets/${placed!.id}/` : `/betslips/${placed!.id}/`;
          await confirmInPlay([path], accessToken);
          return;
        }
      }
    }
    setBusy(false);
  }, [accessToken, legs, mode, legStakes, accaStake, conflictingEvents, applyPriceChange, confirmInPlay]);

  const value: BetslipContextValue = {
    legs, mode, setMode, accaStake, setAccaStake, legStakes, setLegStake,
    combinedOdds, potentialPayout, status, busy, conflictingEvents,
    isOnSlip, isOutcomeOnSlip, toggleLeg, removeLeg, clear, place,
    hasPriceChanges, hasSuspended, acceptPriceChanges,
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
