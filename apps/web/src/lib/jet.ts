'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { useAuth } from '@/lib/auth-context';
import { config } from '@/lib/config';
import { subscribeChannel } from '@/lib/live-board';
import { authedPost } from '@/lib/use-api';

export interface JetSettings {
  enabled: boolean;
  display_name: string;
  house_edge_percent: string;
  rtp_percent: string;
  min_bet: string;
  max_bet: string;
  max_win: string;
  max_multiplier: string;
  round_stake_limit: string;
  betting_seconds: number;
  rate: number;
  /** Simulated players appear in the live bets list (display only). */
  bots_enabled?: boolean;
  chat_enabled?: boolean;
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
  is_free?: boolean;
}

export interface FreeBet { id: number; amount: string; expires_at: string }

export interface ChatMessage { id: number; kind: 'chat' | 'win' | 'rain' | 'system'; name: string; body: string; at: string }

interface JetState {
  settings: JetSettings;
  round: JetRound | null;
  server_time: string;
  history: { id: number; crash_point: string }[];
  bets: JetBet[];
  my_bets: JetBet[];
  balance: string | null;
  free_bets?: FreeBet[];
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
  if (x >= 10) return 'text-[#c017b4] bg-black/50';
  if (x >= 2) return 'text-[#913ef8] bg-black/50';
  return 'text-[#34b4ff] bg-black/50';
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
      const get = (token: string | null) => fetch(`${config.apiUrl}/jet/state/`, {
        headers: token ? { Authorization: `Bearer ${token}` } : {}, cache: 'no-store',
      });
      let res = await get(accessToken);
      // An expired login makes the API refuse even this public read — still show the game.
      if (res.status === 401 && accessToken) res = await get(null);
      if (!res.ok) {
        setError(res.status === 404
          ? 'The game isn’t switched on yet — check back soon.'
          : `The game is having a moment (error ${res.status}) — retrying…`);
        return;
      }
      const data = (await res.json()) as JetState;
      offset.current = Date.parse(data.server_time) - Date.now();
      setState(data);
      setError(null);
    } catch {
      setError('Can’t reach the game right now — check your connection. Retrying…');
    }
  }, [accessToken]);

  useEffect(() => { void load(); }, [load]);

  // Realtime frames.
  useEffect(() => subscribeChannel('jet', (raw) => {
    let msg: {
      type: string; round?: JetRound | number; bet?: JetBet | number; server_time?: string;
      bets?: [number, string, string][];
    };
    try { msg = JSON.parse(raw); } catch { return; }
    lastFrame.current = Date.now();
    if (msg.server_time) offset.current = Date.parse(msg.server_time) - Date.now();
    setState((prev) => {
      if (!prev) return prev;
      // Simulated players joining ([id, name, stake]) or cashing out ([id, x, payout]).
      if ((msg.type === 'bots' || msg.type === 'bot_cashouts') && msg.bets && msg.round === prev.round?.id) {
        const roundId = msg.round as number;
        if (msg.type === 'bots') {
          const known = new Set(prev.bets.map((b) => b.id));
          const fresh: JetBet[] = msg.bets.filter(([id]) => !known.has(id)).map(([id, player, stake]) => ({
            id, round: roundId, player, slot: 1, stake, status: 'active', cashout_multiplier: null, payout: '0',
          }));
          return { ...prev, bets: [...prev.bets, ...fresh].sort((a, b) => Number(b.stake) - Number(a.stake)) };
        }
        const done = new Map(msg.bets.map(([id, x, payout]) => [id, { x, payout }]));
        return {
          ...prev,
          bets: prev.bets.map((b) => {
            const d = done.get(b.id);
            return d ? { ...b, status: 'cashed' as const, cashout_multiplier: d.x, payout: d.payout } : b;
          }),
        };
      }
      if (typeof msg.round === 'number') return prev;
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
    // A rain may have dropped a free bet on this player.
    if (msg.type === 'round' || msg.type === 'crash' || msg.type === 'rain') void load();
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
    const res = await authedPost<{ bet: JetBet; balance: string; free_bets?: FreeBet[] }>(path, body, accessToken);
    if (res.data) {
      const { bet, balance, free_bets: freeBets } = res.data;
      setState((prev) => {
        if (!prev) return prev;
        const upsert = (list: JetBet[]) => (list.some((b) => b.id === bet.id)
          ? list.map((b) => (b.id === bet.id ? bet : b))
          : [...list, bet]);
        const drop = bet.status === 'refunded';
        return {
          ...prev, balance, free_bets: freeBets ?? prev.free_bets,
          my_bets: drop ? prev.my_bets.filter((b) => b.id !== bet.id) : upsert(prev.my_bets),
          bets: drop ? prev.bets.filter((b) => b.id !== bet.id) : upsert(prev.bets),
        };
      });
      window.dispatchEvent(new Event('slyk:wallet-changed'));
      // Played inside the /aviator frame: let the page around it refresh its balance too.
      if (window.parent !== window) window.parent.postMessage({ type: 'slyk:wallet-changed' }, window.location.origin);
    }
    return { error: res.error };
  }, [accessToken]);

  return {
    state, error, now, reload: load,
    placeBet: (slot: number, stake: string, autoCashout: string | null, freeBetId?: number) =>
      act('/jet/bets/', {
        slot, stake, ...(autoCashout ? { auto_cashout: autoCashout } : {}), ...(freeBetId ? { free_bet_id: freeBetId } : {}),
      }),
    cancelBet: (id: number) => act(`/jet/bets/${id}/cancel/`),
    cashOut: (id: number) => act(`/jet/bets/${id}/cashout/`),
  };
}

/** The game's chat lobby: recent messages, then live ones from the `jet` channel. */
export function useJetChat() {
  const { accessToken } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [enabled, setEnabled] = useState(true);

  const load = useCallback(async () => {
    try {
      const res = await fetch(`${config.apiUrl}/jet/chat/`, { cache: 'no-store' });
      if (!res.ok) return;
      const data = (await res.json()) as { enabled: boolean; messages: ChatMessage[] };
      setEnabled(data.enabled);
      setMessages(data.messages);
    } catch { /* the next poll retries */ }
  }, []);

  useEffect(() => {
    void load();
    const t = window.setInterval(() => { if (document.visibilityState === 'visible') void load(); }, 20000);
    return () => window.clearInterval(t);
  }, [load]);

  useEffect(() => subscribeChannel('jet', (raw) => {
    let msg: { type: string; message?: ChatMessage; id?: number };
    try { msg = JSON.parse(raw); } catch { return; }
    if (msg.type === 'chat' && msg.message) {
      const m = msg.message;
      setMessages((prev) => (prev.some((x) => x.id === m.id) ? prev : [...prev, m].slice(-100)));
    } else if (msg.type === 'chat_hide') {
      setMessages((prev) => prev.filter((x) => x.id !== msg.id));
    }
  }), []);

  const send = useCallback(async (body: string): Promise<{ error?: string }> => {
    if (!accessToken) return { error: 'Log in to chat.' };
    const res = await authedPost<{ message: ChatMessage }>('/jet/chat/', { body }, accessToken);
    if (res.data) {
      const m = res.data.message;
      setMessages((prev) => (prev.some((x) => x.id === m.id) ? prev : [...prev, m].slice(-100)));
    }
    return { error: res.error };
  }, [accessToken]);

  return { messages, enabled, send };
}
