'use client';

import { useEffect, useState } from 'react';
import { config } from '@/lib/config';
import type { Market } from '@/lib/sports';

interface MarketsFrame {
  type: 'markets';
  markets: { id: number; is_open: boolean; outcomes: { id: number; odds: string; is_open: boolean }[] }[];
}

/**
 * Keeps an event's secondary markets live: merges `type: "markets"` frames from the
 * event's realtime channel (`odds:<id>`) into the server-rendered snapshot. Markets
 * the frame doesn't mention are left as they are.
 */
export function useLiveMarkets(eventId: string | number, initial: Market[]): Market[] {
  const [markets, setMarkets] = useState<Market[]>(initial);

  useEffect(() => { setMarkets(initial); }, [initial]);

  useEffect(() => {
    let closed = false;
    let socket: WebSocket | undefined;
    try {
      socket = new WebSocket(`${config.wsUrl}/odds:${eventId}`);
      socket.onmessage = (ev) => {
        if (closed) return;
        let frame: MarketsFrame;
        try {
          frame = JSON.parse(String(ev.data));
        } catch {
          return; // non-JSON control frames
        }
        if (!frame || frame.type !== 'markets' || !Array.isArray(frame.markets)) return;
        const byId = new Map(frame.markets.map((m) => [m.id, m]));
        setMarkets((prev) => prev.map((m) => {
          const upd = byId.get(m.id);
          if (!upd) return m;
          const outcomes = new Map(upd.outcomes.map((o) => [o.id, o]));
          return {
            ...m,
            is_open: upd.is_open,
            outcomes: m.outcomes.map((o) => {
              const u = outcomes.get(o.id);
              return u ? { ...o, previous_odds: o.odds, odds: u.odds, is_open: u.is_open } : o;
            }),
          };
        }));
      };
    } catch {
      /* realtime unavailable — keep the snapshot */
    }
    return () => {
      closed = true;
      try { socket?.close(); } catch {}
    };
  }, [eventId]);

  return markets;
}
