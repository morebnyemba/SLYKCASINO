'use client';

import { useEffect, useRef, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { config } from '@/lib/config';

type Status = 'connecting' | 'connected' | 'disconnected' | 'error';

/**
 * Generic realtime feed backed by the Erlang WebSocket engine (/ws/).
 * `channel` selects the topic (e.g. "odds", "chat:lobby").
 */
export function LiveFeed({ channel = 'odds', title = 'Live Feed', height = 240 }: {
  channel?: string;
  title?: string;
  height?: number;
}) {
  const [status, setStatus] = useState<Status>('connecting');
  const [items, setItems] = useState<string[]>([]);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let closed = false;
    let socket: WebSocket | undefined;
    try {
      socket = new WebSocket(`${config.wsUrl}/${channel}`);
      socketRef.current = socket;
      socket.onopen = () => !closed && setStatus('connected');
      socket.onclose = () => !closed && setStatus('disconnected');
      socket.onerror = () => !closed && setStatus('error');
      socket.onmessage = (ev) => !closed && setItems((prev) => [String(ev.data), ...prev].slice(0, 50));
    } catch {
      setStatus('error');
    }
    return () => {
      closed = true;
      try { socket?.close(); } catch {}
    };
  }, [channel]);

  const tone = status === 'connected' ? 'success' : status === 'error' ? 'destructive' : 'secondary';

  return (
    <Card>
      <CardHeader className="flex-row items-center justify-between space-y-0 py-3">
        <CardTitle className="text-base">{title}</CardTitle>
        <Badge variant={tone}>● {status}</Badge>
      </CardHeader>
      <CardContent>
        <ul className="overflow-auto font-mono text-xs" style={{ height }}>
          {items.length === 0 && (
            <li className="text-muted-foreground">Waiting for messages on <code>/ws/{channel}</code>…</li>
          )}
          {items.map((m, i) => (<li key={i} className="py-0.5">{m}</li>))}
        </ul>
      </CardContent>
    </Card>
  );
}
