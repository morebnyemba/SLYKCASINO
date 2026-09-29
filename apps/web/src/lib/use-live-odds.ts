'use client';

import { useEffect, useState } from 'react';
import { config } from '@/lib/config';

export interface LiveOdds {
  odds?: number;
  odds_draw?: number | null;
  odds_away?: number | null;
  /** Trading state, pushed with each in-play price update. */
  in_play?: boolean;
  bettable?: boolean;
  main_open?: boolean;
  score_home?: number | null;
  score_away?: number | null;
  elapsed?: number | null;
  status?: string;
}

const STATE_KEYS = ['in_play', 'bettable', 'main_open', 'score_home', 'score_away', 'elapsed', 'status'] as const;

/**
 * Subscribes to an event's realtime odds channel (`odds:<id>`) and returns the
 * latest prices, seeded from the server-rendered snapshot. `live` flips true
 * once a real update arrives. Non-JSON frames (e.g. the "connected:" welcome)
 * are ignored.
 */
export function useLiveOdds(eventId: string | number, initial: LiveOdds): LiveOdds & { live: boolean } {
  const [odds, setOdds] = useState<LiveOdds>(initial);
  // A fresh server render (e.g. the in-play auto-refresh) re-seeds the snapshot.
  const seed = JSON.stringify(initial);
  useEffect(() => { setOdds(JSON.parse(seed) as LiveOdds); }, [seed]);
  const [live, setLive] = useState(false);

  useEffect(() => {
    let closed = false;
    let socket: WebSocket | undefined;
    try {
      socket = new WebSocket(`${config.wsUrl}/odds:${eventId}`);
      socket.onmessage = (ev) => {
        if (closed) return;
        try {
          const data = JSON.parse(String(ev.data));
          if (data && data.odds != null) {
            setOdds((prev) => {
              const next: LiveOdds = {
                ...prev,
                odds: Number(data.odds),
                odds_draw: data.odds_draw != null ? Number(data.odds_draw) : null,
                odds_away: data.odds_away != null ? Number(data.odds_away) : null,
              };
              for (const key of STATE_KEYS) {
                if (key in data) (next as Record<string, unknown>)[key] = data[key];
              }
              return next;
            });
            setLive(true);
          }
        } catch {
          /* ignore non-JSON control frames */
        }
      };
    } catch {
      /* connection unavailable — keep the seeded snapshot */
    }
    return () => {
      closed = true;
      try { socket?.close(); } catch {}
    };
  }, [eventId]);

  return { ...odds, live };
}
