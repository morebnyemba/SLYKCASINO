'use client';

import { useEffect, useRef, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { Button } from '@slyk/ui/components/button';
import { Input } from '@slyk/ui/components/input';
import { config } from '@/lib/config';
import { useAuth } from '@/lib/auth-context';

type Status = 'connecting' | 'connected' | 'disconnected' | 'error';
interface FeedItem { t: string; m: string }

/** Operator-facing realtime monitor + reply bar for a WS channel.
 *
 * `admin:*` channels require a short-lived signed ticket (minted by Django
 * for the current admin) before the realtime engine will admit the join —
 * see common.realtime_auth on the backend.
 */
export function RealtimeFeed({ channel, title, height = 320 }: { channel: string; title: string; height?: number }) {
  const { accessToken } = useAuth();
  const [status, setStatus] = useState<Status>('connecting');
  const [items, setItems] = useState<FeedItem[]>([]);
  const [text, setText] = useState('');
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    if (!accessToken) return;
    let closed = false;
    let socket: WebSocket | undefined;

    (async () => {
      try {
        let wsUrl = `${config.wsUrl}/${channel}`;
        if (channel.startsWith('admin:')) {
          const res = await fetch(
            `${config.apiUrl}/realtime/ticket/?channel=${encodeURIComponent(channel)}`,
            { headers: { Authorization: `Bearer ${accessToken}` }, cache: 'no-store' },
          );
          if (!res.ok) throw new Error('failed to obtain ticket');
          const { ticket } = (await res.json()) as { ticket: string };
          wsUrl += `?ticket=${encodeURIComponent(ticket)}`;
        }
        if (closed) return;
        socket = new WebSocket(wsUrl);
        socketRef.current = socket;
        socket.onopen = () => !closed && setStatus('connected');
        socket.onclose = () => !closed && setStatus('disconnected');
        socket.onerror = () => !closed && setStatus('error');
        socket.onmessage = (ev) =>
          !closed && setItems((prev) => [{ t: new Date().toLocaleTimeString(), m: String(ev.data) }, ...prev].slice(0, 100));
      } catch {
        if (!closed) setStatus('error');
      }
    })();

    return () => { closed = true; try { socket?.close(); } catch {} };
  }, [channel, accessToken]);

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
