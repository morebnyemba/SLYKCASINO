'use client';

import { useEffect, useRef, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { Input } from '@slyk/ui/components/input';
import { config } from '@/lib/config';
import { useAuth } from '@/lib/auth-context';
import { authedPost } from '@/lib/use-api';

interface Message {
  id: number | string;
  sender: string;
  body: string;
  created_at: string;
  player_id?: number | null;
}

type WsStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

const CHANNEL = 'chat:lobby';

export default function LiveChatPage() {
  const { user, accessToken } = useAuth();
  const [messages, setMessages] = useState<Message[]>([]);
  const [wsStatus, setWsStatus] = useState<WsStatus>('connecting');
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const socketRef = useRef<WebSocket | null>(null);

  // Load message history from REST API
  useEffect(() => {
    fetch(`${config.apiUrl}/chat/?channel=lobby`, { cache: 'no-store' })
      .then((r) => r.ok ? r.json() : null)
      .then((data) => {
        if (data?.results) {
          // API returns newest-first; reverse for display
          setMessages([...(data.results as Message[])].reverse());
        }
      })
      .catch(() => {});
  }, []);

  // WebSocket for live incoming messages
  useEffect(() => {
    let closed = false;
    let socket: WebSocket | undefined;
    try {
      socket = new WebSocket(`${config.wsUrl}/${CHANNEL}`);
      socketRef.current = socket;
      socket.onopen = () => !closed && setWsStatus('connected');
      socket.onclose = () => !closed && setWsStatus('disconnected');
      socket.onerror = () => !closed && setWsStatus('error');
      socket.onmessage = (ev) => {
        if (closed) return;
        try {
          const parsed = JSON.parse(String(ev.data)) as Partial<Message>;
          if (parsed.body) {
            setMessages((prev) => [
              ...prev,
              {
                id: `ws-${Date.now()}`,
                sender: parsed.sender ?? 'Player',
                body: parsed.body!,
                created_at: new Date().toISOString(),
              },
            ].slice(-200));
          }
        } catch {
          // Raw string message fallback
          setMessages((prev) => [
            ...prev,
            { id: `ws-${Date.now()}`, sender: '?', body: String(ev.data), created_at: new Date().toISOString() },
          ].slice(-200));
        }
      };
    } catch {
      setWsStatus('error');
    }
    return () => { closed = true; try { socket?.close(); } catch {} };
  }, []);

  // Scroll to bottom on new messages
  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages]);

  async function sendMessage(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim() || !accessToken) return;
    setSending(true);
    const body = text.trim();
    setText('');

    const { data, error } = await authedPost<Message>(
      '/chat/',
      { body, channel: 'lobby' },
      accessToken,
    );

    if (data) {
      setMessages((prev) => [...prev, data].slice(-200));
    } else if (error) {
      setText(body); // restore on failure
    }
    setSending(false);
  }

  const statusTone = wsStatus === 'connected' ? 'default' : wsStatus === 'error' ? 'destructive' : 'secondary';

  return (
    <div className="flex h-[calc(100vh-140px)] flex-col gap-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">Live Chat</h1>
          <p className="text-muted-foreground text-sm">Chat with support and other players.</p>
        </div>
        <Badge variant={statusTone}>● {wsStatus}</Badge>
      </div>

      <Card className="flex flex-1 flex-col overflow-hidden">
        {/* Message list */}
        <CardContent className="flex-1 overflow-y-auto p-4 space-y-3">
          {messages.length === 0 && (
            <p className="text-center text-sm text-muted-foreground pt-8">
              No messages yet — be the first to say hello!
            </p>
          )}
          {messages.map((m) => {
            const isMe = user && m.sender === user.username;
            return (
              <div key={m.id} className={`flex gap-2 ${isMe ? 'flex-row-reverse' : ''}`}>
                <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold ${isMe ? 'bg-primary text-primary-foreground' : 'bg-muted text-muted-foreground'}`}>
                  {m.sender[0]?.toUpperCase() ?? '?'}
                </div>
                <div className={`max-w-[75%] rounded-2xl px-4 py-2 text-sm ${isMe ? 'rounded-tr-sm bg-primary text-primary-foreground' : 'rounded-tl-sm bg-muted'}`}>
                  {!isMe && (
                    <p className="mb-0.5 text-xs font-semibold text-muted-foreground">{m.sender}</p>
                  )}
                  <p>{m.body}</p>
                  <p className={`mt-0.5 text-[10px] ${isMe ? 'text-primary-foreground/70' : 'text-muted-foreground'}`}>
                    {new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                  </p>
                </div>
              </div>
            );
          })}
          <div ref={bottomRef} />
        </CardContent>

        {/* Send bar */}
        <div className="border-t border-border p-3">
          {user ? (
            <form onSubmit={sendMessage} className="flex gap-2">
              <Input
                value={text}
                onChange={(e) => setText(e.target.value)}
                placeholder="Type a message…"
                disabled={sending}
                autoFocus
              />
              <button
                type="submit"
                disabled={sending || !text.trim()}
                className="rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
              >
                Send
              </button>
            </form>
          ) : (
            <p className="text-center text-sm text-muted-foreground">
              <a href="/login" className="text-primary hover:underline">Log in</a> to send messages.
            </p>
          )}
        </div>
      </Card>
    </div>
  );
}
