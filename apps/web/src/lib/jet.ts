'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { config } from '@/lib/config';
import { subscribeChannel } from '@/lib/live-board';
import { authedPost } from '@/lib/use-api';

export interface JetSettings {
  enabled: boolean;
  house_edge_percent: string;
  rtp_percent: string;
  min_bet: string;
  max_bet: string;
  max_win: string;
  max_multiplier: string;
  round_stake_limit: string;
  betting_seconds: number;
  rate: number;
}

export interface JetRound {
  id: number;
  status: 'betting' | 'flying' | 'crashed';
  seed_hash: string;
  betting_ends_at: string;
  started_at: string | null;
  crashed_at: string | null;
  crash_point: string | null;
  server_seed: string | null;
  bet_count: number;
  total_stake: string;
}

export interface JetBet {
  id: number;
  round: number;
  player: string;
  slot: number;
  stake: string;
  status: 'active' | 'cashed' | 'lost' | 'refunded';
  cashout_multiplier: string | null;
  payout: string;
  auto_cashout?: string | null;
}

interface JetState {
  settings: JetSettings;
  round: JetRound | null;
  server_time: string;
  history: { id: number; crash_point: string }[];
  bets: JetBet[];
  my_bets: JetBet[];
  balance: string | null;
}

/** Multiplier after `seconds` of flight — the same curve the server pays on. */
export function multiplierAt(seconds: number, rate: number): number {
  return seconds <= 0 ? 1 : Math.floor(Math.exp(rate * seconds) * 100) / 100;
}

export function fmtX(v: number | string | null | undefined): string {
  return `${Number(v ?? 0).toFixed(2)}x`;
}

/** Colour band for a crash point, as crash games show history. */
export function crashTone(x: number): string {
  if (x >= 10) return 'text-[#e879f9] bg-[#e879f9]/10';
  if (x >= 2) return 'text-[#a78bfa] bg-[#a78bfa]/10';
  return 'text-[#38bdf8] bg-[#38bdf8]/10';
}

/**
 * Re-derive a finished round's crash point in the browser from its revealed
 * seed — exactly as the server does — so players can check every round.
 */
export async function verifyRound(seed: string, roundId: number, houseEdgePercent: number, cap: number): Promise<{ hashOk: (hash: string) => Promise<boolean>; crash: number }> {
  const enc = new TextEncoder();
  const key = await crypto.subtle.importKey('raw', enc.encode(seed), { name: 'HMAC', hash: 'SHA-256' }, false, ['sign']);
  const sig = new Uint8Array(await crypto.subtle.sign('HMAC', key, enc.encode(`jet:${roundId}`)));
  const hex = Array.from(sig, (b) => b.toString(16).padStart(2, '0')).join('');
  const r = parseInt(hex.slice(0, 13), 16) / 2 ** 52;
  const raw = Math.floor((100 * (1 - houseEdgePercent / 100)) / (1 - r)) / 100;
  const crash = Math.max(1, Math.min(raw, cap));
  const hashOk = async (hash: string) => {
    const digest = new Uint8Array(await crypto.subtle.digest('SHA-256', enc.encode(seed)));
    return Array.from(digest, (b) => b.toString(16).padStart(2, '0')).join('') === hash;
  };
  return { hashOk, crash };
}

/**
 * Live game state: an initial snapshot from /jet/state/, then realtime frames
 * from the `jet` channel, with a light poll as a safety net (and the only
 * source when realtime is off). `now()` is the server clock.
 */
export function useJet() {
  const { accessToken } = useAuth();
  const [state, setState] = useState<JetState | null>(null);
  const [error, setError] = useState<string | null>(null);
  const offset = useRef(0); // server time - local time, ms
  const lastFrame = useRef(0);

  const now = useCallback(() => Date.now() + offset.current, []);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${config.apiUrl}/jet/state/`, {
        headers: accessToken ? { Authorization: `Bearer ${accessToken}` } : {}, cache: 'no-store',
      });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = (await res.json()) as JetState;
      offset.current = Date.parse(data.server_time) - Date.now();
      setState(data);
      setError(null);
    } catch {
      setError('Can’t reach the game right now — retrying…');
    }
  }, [accessToken]);

  useEffect(() => { void load(); }, [load]);

  // Realtime frames.
  useEffect(() => subscribeChannel('jet', (raw) => {
    let msg: { type: string; round?: JetRound; bet?: JetBet | number; server_time?: string };
    try { msg = JSON.parse(raw); } catch { return; }
    lastFrame.current = Date.now();
    if (msg.server_time) offset.current = Date.parse(msg.server_time) - Date.now();
    setState((prev) => {
      if (!prev) return prev;
      if (msg.type === 'round' && msg.round) {
        const fresh = msg.round.id !== prev.round?.id;
        return { ...prev, round: msg.round, bets: fresh ? [] : prev.bets, my_bets: fresh ? [] : prev.my_bets };
      }
      if (msg.type === 'crash' && msg.round) {
        const r = msg.round;
        const settle = (b: JetBet) => (b.status === 'active' ? { ...b, status: 'lost' as const } : b);
        return {
          ...prev, round: r,
          history: [{ id: r.id, crash_point: r.crash_point ?? '1.00' }, ...prev.history.filter((h) => h.id !== r.id)].slice(0, 40),
          bets: prev.bets.map(settle), my_bets: prev.my_bets.map(settle),
        };
      }
      if ((msg.type === 'bet' || msg.type === 'cashout') && msg.bet && typeof msg.bet === 'object') {
        const bet = msg.bet;
        if (bet.round !== prev.round?.id) return prev;
        const merge = (list: JetBet[]) => {
          const i = list.findIndex((b) => b.id === bet.id);
          return i >= 0 ? list.map((b) => (b.id === bet.id ? { ...b, ...bet } : b)) : null;
        };
        return {
          ...prev,
          bets: merge(prev.bets) ?? [...prev.bets, bet].sort((a, b) => Number(b.stake) - Number(a.stake)),
          my_bets: merge(prev.my_bets) ?? prev.my_bets,
        };
      }
      if (msg.type === 'cancel' && typeof msg.bet === 'number') {
        return { ...prev, bets: prev.bets.filter((b) => b.id !== msg.bet) };
      }
      if (msg.type === 'paused') return { ...prev, settings: { ...prev.settings, enabled: false } };
      return prev;
    });
    if (msg.type === 'round' || msg.type === 'crash') void load();
  }), [load]);

  // Safety net: poll faster while flying if realtime has gone quiet.
  useEffect(() => {
    const timer = window.setInterval(() => {
      if (document.visibilityState !== 'visible') return;
      const quiet = Date.now() - lastFrame.current > 6000;
      const flying = state?.round?.status === 'flying';
      if (quiet || !state) void load();
      else if (flying && Date.now() - lastFrame.current > 2500) void load();
    }, 1000);
    return () => window.clearInterval(timer);
  }, [load, state]);

  const act = useCallback(async (path: string, body: unknown = {}) => {
    if (!accessToken) return { error: 'Log in to play.' };
    const res = await authedPost<{ bet: JetBet; balance: string }>(path, body, accessToken);
    if (res.data) {
      const { bet, balance } = res.data;
      setState((prev) => {
        if (!prev) return prev;
        const upsert = (list: JetBet[]) => (list.some((b) => b.id === bet.id)
          ? list.map((b) => (b.id === bet.id ? bet : b))
          : [...list, bet]);
        const drop = bet.status === 'refunded';
        return {
          ...prev, balance,
          my_bets: drop ? prev.my_bets.filter((b) => b.id !== bet.id) : upsert(prev.my_bets),
          bets: drop ? prev.bets.filter((b) => b.id !== bet.id) : upsert(prev.bets),
        };
      });
      window.dispatchEvent(new Event('slyk:wallet-changed'));
    }
    return { error: res.error };
  }, [accessToken]);

  return {
    state, error, now, reload: load,
    placeBet: (slot: number, stake: string, autoCashout: string | null) =>
      act('/jet/bets/', { slot, stake, ...(autoCashout ? { auto_cashout: autoCashout } : {}) }),
    cancelBet: (id: number) => act(`/jet/bets/${id}/cancel/`),
    cashOut: (id: number) => act(`/jet/bets/${id}/cashout/`),
  };
}
