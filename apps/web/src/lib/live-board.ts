'use client';

import { useCallback, useMemo, useSyncExternalStore } from 'react';
import { config } from '@/lib/config';
import type { EventItem } from '@/lib/sports';

/**
 * Live state for every event on screen, over ONE shared WebSocket (`odds:board`)
 * however many rows are listed. The server publishes a compact frame each time
 * an event's prices, score, clock or trading state change; rows merge the latest
 * frame over their server-rendered snapshot.
 *
 * The socket opens with the first subscriber, keeps itself alive (the realtime
 * server drops idle sockets after 60s) and reconnects with backoff.
 */

export interface BoardFrame {
  event_id: number;
  odds?: string | null;
  odds_draw?: string | null;
  odds_away?: string | null;
  previous_odds?: string | null;
  has_odds?: boolean;
  status?: string;
  elapsed?: number | null;
  score_home?: number | null;
  score_away?: number | null;
  in_play?: boolean;
  bettable?: boolean;
  main_open?: boolean;
}

type Listener = () => void;

const frames = new Map<string, BoardFrame>();
const listeners = new Map<string, Set<Listener>>();
const anyListeners = new Set<(frame: BoardFrame) => void>();
let socket: WebSocket | null = null;
let keepalive: ReturnType<typeof setInterval> | undefined;
let retry: ReturnType<typeof setTimeout> | undefined;
let backoff = 1000;
let subscribers = 0;

function connect() {
  if (typeof window === 'undefined' || socket || subscribers === 0) return;
  try {
    socket = new WebSocket(`${config.wsUrl}/odds:board`);
  } catch {
    scheduleReconnect();
    return;
  }
  socket.onopen = () => {
    backoff = 1000;
    // Any text keeps the socket alive; odds channels drop client text server-side.
    keepalive = setInterval(() => { try { socket?.send('ping'); } catch { /* reconnect handles it */ } }, 25000);
  };
  socket.onmessage = (msg) => {
    let frame: BoardFrame & { type?: string };
    try { frame = JSON.parse(String(msg.data)); } catch { return; } // "connected:" welcome
    if (!frame || frame.type !== 'event' || frame.event_id == null) return;
    const id = String(frame.event_id);
    frames.set(id, frame);
    listeners.get(id)?.forEach((l) => l());
    anyListeners.forEach((l) => l(frame));
  };
  socket.onclose = () => {
    clearInterval(keepalive);
    socket = null;
    scheduleReconnect();
  };
  socket.onerror = () => { try { socket?.close(); } catch { /* ignore */ } };
}

function scheduleReconnect() {
  if (subscribers === 0 || retry) return;
  retry = setTimeout(() => { retry = undefined; connect(); }, backoff);
  backoff = Math.min(backoff * 2, 30000);
}

function retain() {
  subscribers += 1;
  connect();
  return () => {
    subscribers -= 1;
    if (subscribers === 0) {
      clearTimeout(retry); retry = undefined;
      clearInterval(keepalive);
      try { socket?.close(); } catch { /* ignore */ }
      socket = null;
    }
  };
}

function subscribe(id: string, listener: Listener) {
  let set = listeners.get(id);
  if (!set) { set = new Set(); listeners.set(id, set); }
  set.add(listener);
  const release = retain();
  return () => { set!.delete(listener); release(); };
}

/** Every frame as it arrives (e.g. the bet slip re-checking its prices). */
export function onBoardFrame(listener: (frame: BoardFrame) => void): () => void {
  anyListeners.add(listener);
  const release = retain();
  return () => { anyListeners.delete(listener); release(); };
}

/**
 * A standalone subscription to one realtime channel (e.g. a match's own
 * `odds:<id>`), with the same keepalive and reconnect-with-backoff as the board.
 * Returns an unsubscribe function.
 */
export function subscribeChannel(channel: string, onMessage: (data: string) => void): () => void {
  let ws: WebSocket | null = null;
  let ping: ReturnType<typeof setInterval> | undefined;
  let again: ReturnType<typeof setTimeout> | undefined;
  let delay = 1000;
  let closed = false;

  const open = () => {
    if (closed) return;
    try {
      ws = new WebSocket(`${config.wsUrl}/${channel}`);
    } catch {
      again = setTimeout(open, delay);
      delay = Math.min(delay * 2, 30000);
      return;
    }
    ws.onopen = () => {
      delay = 1000;
      ping = setInterval(() => { try { ws?.send('ping'); } catch { /* reconnect handles it */ } }, 25000);
    };
    ws.onmessage = (msg) => { if (!closed) onMessage(String(msg.data)); };
    ws.onclose = () => {
      clearInterval(ping);
      ws = null;
      if (!closed) {
        again = setTimeout(open, delay);
        delay = Math.min(delay * 2, 30000);
      }
    };
    ws.onerror = () => { try { ws?.close(); } catch { /* ignore */ } };
  };
  open();
  return () => {
    closed = true;
    clearTimeout(again);
    clearInterval(ping);
    try { ws?.close(); } catch { /* ignore */ }
  };
}

const PRICE_FIELDS = ['odds', 'odds_draw', 'odds_away'] as const;

/**
 * An event row's live view: the server snapshot with the latest board frame
 * applied, plus which way each 1X2 price last moved since the page loaded.
 */
export function useLiveEvent(ev: EventItem): { ev: EventItem; moves: Partial<Record<'home' | 'draw' | 'away', 'up' | 'down'>> } {
  const id = String(ev.id);
  const sub = useCallback((l: Listener) => subscribe(id, l), [id]);
  const frame = useSyncExternalStore(sub, () => frames.get(id), () => undefined);

  return useMemo(() => {
    if (!frame) return { ev, moves: {} };
    const merged: EventItem = { ...ev };
    for (const [key, value] of Object.entries(frame)) {
      if (key !== 'event_id' && key !== 'type' && value !== undefined) {
        (merged as unknown as Record<string, unknown>)[key] = value;
      }
    }
    const moves: Partial<Record<'home' | 'draw' | 'away', 'up' | 'down'>> = {};
    const names = { odds: 'home', odds_draw: 'draw', odds_away: 'away' } as const;
    for (const field of PRICE_FIELDS) {
      const before = Number(ev[field]);
      const now = Number(frame[field]);
      if (Number.isFinite(before) && Number.isFinite(now) && before !== now) {
        moves[names[field]] = now > before ? 'up' : 'down';
      }
    }
    return { ev: merged, moves };
  }, [ev, frame]);
}
