'use client';

import { useEffect, useRef, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { Button } from '@slyk/ui/components/button';
import { Input } from '@slyk/ui/components/input';
import { config } from '@/lib/config';

type Status = 'connecting' | 'connected' | 'disconnected' | 'error';
interface FeedItem { t: string; m: string }

/** Operator-facing realtime monitor + reply bar for a WS channel. */
export function RealtimeFeed({ channel, title, height = 320 }: { channel: string; title: string; height?: number }) {
  const [status, setStatus] = useState<Status>('connecting');
  const [items, setItems] = useState<FeedItem[]>([]);
  const [text, setText] = useState('');
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
      socket.onmessage = (ev) =>
        !closed && setItems((prev) => [{ t: new Date().toLocaleTimeString(), m: String(ev.data) }, ...prev].slice(0, 100));
    } catch {
      setStatus('error');
    }
    return () => { closed = true; try { socket?.close(); } catch {} };
  }, [channel]);

  const tone = status === 'connected' ? 'success' : status === 'error' ? 'destructive' : 'secondary';

  function send(e: React.FormEvent) {
    e.preventDefault();
    if (!text) return;
    try { socketRef.current?.send(text); } catch {}
    setText('');
  }

  return (
    <Card className="overflow-hidden">
      <CardHeader className="flex-row items-center justify-between space-y-0 py-3">
        <CardTitle className="text-base">{title}</CardTitle>
        <Badge variant={tone}>● {status} — /ws/{channel}</Badge>
      </CardHeader>
      <CardContent className="space-y-3">
        <ul className="overflow-auto font-mono text-xs" style={{ height }}>
          {items.length === 0 && <li className="text-muted-foreground">Awaiting events…</li>}
          {items.map((it, i) => (
            <li key={i} className="py-0.5"><span className="text-muted-foreground">{it.t}</span> {it.m}</li>
          ))}
        </ul>
        <form onSubmit={send} className="flex gap-2">
          <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Send a message to the channel…" />
          <Button type="submit">Send</Button>
        </form>
      </CardContent>
    </Card>
  );
}
