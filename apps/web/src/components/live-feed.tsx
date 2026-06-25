'use client';

import { useEffect, useRef, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { config } from '@/lib/config';

type Status = 'connecting' | 'connected' | 'disconnected' | 'error';
type Move = 'up' | 'down' | 'flat';

interface FeedRow {
  key: number;
  event: string;
  odds: number | null;
  move: Move;
}

let nextKey = 0;

/** Parses a raw WS frame into an {event, odds} pair, or null if it isn't a price update.
 *  Handles the per-event JSON snapshot (`{name, odds, ...}`) and the global ticker's
 *  plain "<event name>: <odds>" line — both published by `services.publish_event_odds`. */
function parseFrame(raw: string): { event: string; odds: number } | null {
  try {
    const data = JSON.parse(raw);
    if (data && data.odds != null && data.name) {
      return { event: String(data.name), odds: Number(data.odds) };
    }
  } catch {
    /* not JSON — fall through to the plain-text ticker format */
  }
  const match = raw.match(/^(.*):\s*([\d.]+)\s*$/);
  if (match) {
    return { event: match[1].trim(), odds: Number(match[2]) };
  }
  return null;
}

/**
 * Realtime odds ticker backed by the Erlang WebSocket engine (/ws/). `channel`
 * selects the topic — the global "odds" line or a single event's "odds:<id>".
 * Shows each update as event / current price / move-vs-previous-price arrow.
 */
export function LiveFeed({ channel = 'odds', title = 'Live Feed', height = 240 }: {
  channel?: string;
  title?: string;
  height?: number;
}) {
  const [status, setStatus] = useState<Status>('connecting');
  const [rows, setRows] = useState<FeedRow[]>([]);
  const socketRef = useRef<WebSocket | null>(null);
  const lastOddsRef = useRef<Map<string, number>>(new Map());

  useEffect(() => {
    let closed = false;
    let socket: WebSocket | undefined;
    try {
      socket = new WebSocket(`${config.wsUrl}/${channel}`);
      socketRef.current = socket;
      socket.onopen = () => !closed && setStatus('connected');
      socket.onclose = () => !closed && setStatus('disconnected');
      socket.onerror = () => !closed && setStatus('error');
      socket.onmessage = (ev) => {
        if (closed) return;
        const parsed = parseFrame(String(ev.data));
        if (!parsed) return;
        const prev = lastOddsRef.current.get(parsed.event);
        const move: Move = prev == null || prev === parsed.odds ? 'flat' : parsed.odds > prev ? 'up' : 'down';
        lastOddsRef.current.set(parsed.event, parsed.odds);
        setRows((p) => [{ key: nextKey++, event: parsed.event, odds: parsed.odds, move }, ...p].slice(0, 50));
      };
    } catch {
      setStatus('error');
    }
    return () => {
      closed = true;
      try { socket?.close(); } catch {}
    };
  }, [channel]);

  return (
    <Card>
      <CardHeader className="flex-row items-center gap-2 space-y-0 border-b border-border py-3">
        <span
          className={`h-1.5 w-1.5 rounded-full ${status === 'connected' ? 'animate-pulse bg-win' : 'bg-muted-foreground'}`}
        />
        <CardTitle className="text-xs font-extrabold uppercase tracking-wide">{title}</CardTitle>
      </CardHeader>
      <CardContent className="p-0">
        <ul className="overflow-auto" style={{ height }}>
          {rows.length === 0 && (
            <li className="px-4 py-3 text-xs text-muted-foreground">Waiting for live odds updates…</li>
          )}
          {rows.map((r) => (
            <li key={r.key} className="flex items-center gap-2.5 px-4 py-2 text-[11.5px]">
              <span className="flex-1 truncate text-muted-foreground">{r.event}</span>
              <span className="font-mono text-[12.5px] font-bold">{r.odds?.toFixed(2)}</span>
              <span
                className={`text-[11px] font-bold ${
                  r.move === 'up' ? 'text-win' : r.move === 'down' ? 'text-down' : 'text-transparent'
                }`}
              >
                {r.move === 'up' ? '▲' : r.move === 'down' ? '▼' : '—'}
              </span>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
