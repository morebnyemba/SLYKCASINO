'use client';

import { useEffect, useState } from 'react';
import { subscribeChannel } from '@/lib/live-board';

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

  useEffect(() => subscribeChannel(`odds:${eventId}`, (raw) => {
    let data: Record<string, unknown>;
    try { data = JSON.parse(raw); } catch { return; } // "connected:" welcome
    if (!data || data.odds == null || data.type === 'markets') return;
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
  }), [eventId]);

  return { ...odds, live };
}
