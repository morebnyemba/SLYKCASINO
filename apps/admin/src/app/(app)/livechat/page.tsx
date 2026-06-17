'use client';

import { useEffect, useRef, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { Input } from '@slyk/ui/components/input';
import { config } from '@/lib/config';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';

interface Message {
  id: number | string;
  sender: string;
  body: string;
  channel: string;
  created_at: string;
}

interface HistoryResponse { results?: Message[] }

type WsStatus = 'connecting' | 'connected' | 'disconnected' | 'error';

const CHANNELS = ['chat:lobby', 'chat:support'];

function ChatPane({ channel, label }: { channel: string; label: string }) {
  const { accessToken } = useAuth();
  const { data } = useApi<HistoryResponse>(`/chat/?channel=${channel.replace('chat:', '')}`);
  const history: Message[] = data?.results ? [...data.results].reverse() : [];

  const [live, setLive] = useState<Message[]>([]);
  const [wsStatus, setWsStatus] = useState<WsStatus>('connecting');
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const bottomRef = useRef<HTMLDivElement>(null);
  const socketRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    let closed = false;
    let socket: WebSocket | undefined;
    try {
      socket = new WebSocket(`${config.wsUrl}/${channel}`);
      socketRef.current = socket;
      socket.onopen = () => !closed && setWsStatus('connected');
      socket.onclose = () => !closed && setWsStatus('disconnected');
      socket.onerror = () => !closed && setWsStatus('error');
      socket.onmessage = (ev) => {
        if (closed) return;
        try {
          const parsed = JSON.parse(String(ev.data)) as Partial<Message>;
          if (parsed.body) {
            setLive((prev) => [...prev, {
              id: `ws-${Date.now()}`,
              sender: parsed.sender ?? '?',
              body: parsed.body!,
              channel,
              created_at: new Date().toISOString(),
            }].slice(-200));
          }
        } catch {
          setLive((prev) => [...prev, {
            id: `ws-${Date.now()}`, sender: '?', body: String(ev.data),
            channel, created_at: new Date().toISOString(),
          }].slice(-200));
        }
      };
    } catch {
      setWsStatus('error');
    }
    return () => { closed = true; try { socket?.close(); } catch {} };
  }, [channel]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [history, live]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!text.trim() || !accessToken) return;
    setSending(true);
    const body = text.trim();
    setText('');
    const { data: msg } = await authedPost<Message>(
      '/chat/',
      { body, channel: channel.replace('chat:', '') },
      accessToken,
    );
    if (msg) setLive((prev) => [...prev, msg]);
    setSending(false);
  }

  const allMessages = [...history, ...live];
  const statusTone = wsStatus === 'connected' ? 'default' : wsStatus === 'error' ? 'destructive' : 'secondary';

  return (
    <Card className="flex flex-col" style={{ height: 480 }}>
      <CardHeader className="flex-row items-center justify-between space-y-0 py-3">
        <CardTitle className="text-sm font-semibold">{label}</CardTitle>
        <Badge variant={statusTone}>● {wsStatus}</Badge>
      </CardHeader>

      <CardContent className="flex flex-1 flex-col overflow-hidden p-0">
        <div className="flex-1 overflow-y-auto px-4 py-2 space-y-2 text-sm">
          {allMessages.length === 0 && (
            <p className="text-muted-foreground text-xs pt-4 text-center">No messages yet.</p>
          )}
          {allMessages.map((m) => (
            <div key={m.id} className="flex gap-2">
              <div className="h-6 w-6 shrink-0 rounded-full bg-muted flex items-center justify-center text-[10px] font-bold text-muted-foreground">
                {m.sender[0]?.toUpperCase() ?? '?'}
              </div>
              <div>
                <span className="font-medium">{m.sender}</span>
                <span className="ml-2 text-muted-foreground">{m.body}</span>
                <span className="ml-2 text-[10px] text-muted-foreground">
                  {new Date(m.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
            </div>
          ))}
          <div ref={bottomRef} />
        </div>

        <div className="border-t border-border p-3">
          <form onSubmit={send} className="flex gap-2">
            <Input
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder="Reply as support…"
              disabled={sending}
              className="text-sm"
            />
            <button
              type="submit"
              disabled={sending || !text.trim()}
              className="rounded-md bg-primary px-3 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
            >
              Send
            </button>
          </form>
        </div>
      </CardContent>
    </Card>
  );
}

export default function LiveChatConsolePage() {
  return (
    <div>
      <h1 className="text-2xl font-bold">Live Chat Console</h1>
      <p className="mb-5 text-muted-foreground">Monitor and respond to player conversations in real time.</p>
      <div className="grid gap-5 lg:grid-cols-2">
        <ChatPane channel="chat:lobby" label="Lobby" />
        <ChatPane channel="chat:support" label="Support Queue" />
      </div>
    </div>
  );
}
