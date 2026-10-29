'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { FaHeadset, FaLock, FaPaperPlane, FaWhatsapp } from 'react-icons/fa';
import { Card } from '@slyk/ui/components/card';
import { Input } from '@slyk/ui/components/input';
import { Spinner } from '@slyk/ui/components/spinner';
import { useWhatsAppSupport } from '@/components/whatsapp-support';
import { useAuth } from '@/lib/auth-context';
import { config } from '@/lib/config';
import { authedPost } from '@/lib/use-api';

interface Message { id: number; body: string; from_staff: boolean; sender: string; created_at: string; read: boolean }

const POLL_MS = 5000;

/** Private support: the player's own conversation with the support team.
 *  Nobody but this player and BetBlits staff can read it. */
export default function SupportChatPage() {
  const { user, accessToken } = useAuth();
  const [messages, setMessages] = useState<Message[] | null>(null);
  const [text, setText] = useState('');
  const [sending, setSending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const lastCount = useRef(0);
  const whatsapp = useWhatsAppSupport();

  const load = useCallback(async () => {
    if (!accessToken) return;
    try {
      const res = await fetch(`${config.apiUrl}/support/messages/`, {
        headers: { Authorization: `Bearer ${accessToken}` }, cache: 'no-store',
      });
      if (res.ok) setMessages(((await res.json()) as { results: Message[] }).results);
    } catch { /* the next poll retries */ }
  }, [accessToken]);

  useEffect(() => {
    void load();
    const t = window.setInterval(() => { if (document.visibilityState === 'visible') void load(); }, POLL_MS);
    return () => window.clearInterval(t);
  }, [load]);

  // Scroll to the newest message when one arrives.
  useEffect(() => {
    const n = messages?.length ?? 0;
    // Scroll the message box only — never the page.
    if (n !== lastCount.current && box.current) box.current.scrollTop = box.current.scrollHeight;
    lastCount.current = n;
  }, [messages]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const body = text.trim();
    if (!body || !accessToken) return;
    setSending(true); setError(null);
    const res = await authedPost<Message>('/support/messages/', { body }, accessToken);
    setSending(false);
    if (res.error) { setError(res.error); return; }
    setText('');
    if (res.data) setMessages((prev) => [...(prev ?? []), res.data!]);
  }

  return (
    <div className="mx-auto flex h-[calc(100vh-140px)] max-w-3xl flex-col gap-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-2xl font-bold"><FaHeadset className="text-secondary" /> Support chat</h1>
          <p className="flex items-center gap-1.5 text-sm text-muted-foreground">
            <FaLock size={11} /> Private — only you and the BetBlits support team can see this conversation.
          </p>
        </div>
        {whatsapp && (
          <a href={whatsapp} target="_blank" rel="noopener noreferrer"
            className="inline-flex items-center gap-1.5 rounded-full border border-border px-3 py-1.5 text-xs font-semibold hover:bg-muted">
            <FaWhatsapp size={13} className="text-[#25D366]" /> Prefer WhatsApp? Chat with us
          </a>
        )}
      </div>

      <Card className="flex flex-1 flex-col overflow-hidden rounded-2xl">
        <div ref={box} className="flex-1 space-y-3 overflow-y-auto p-4">
          {!user ? (
            <div className="flex h-full flex-col items-center justify-center gap-3 text-center text-sm text-muted-foreground">
              <p>Log in to chat privately with our support team about your account, deposits or withdrawals.</p>
              <div className="flex gap-2">
                <Link href="/login" className="rounded-full bg-secondary px-4 py-2 font-bold text-secondary-foreground">Log in</Link>
                {whatsapp && (
                  <a href={whatsapp} target="_blank" rel="noopener noreferrer"
                    className="inline-flex items-center gap-1.5 rounded-full border border-border px-4 py-2 font-semibold">
                    <FaWhatsapp className="text-[#25D366]" /> Chat on WhatsApp
                  </a>
                )}
              </div>
            </div>
          ) : messages === null ? (
            <div className="flex h-full items-center justify-center"><Spinner size={20} /></div>
          ) : messages.length === 0 ? (
            <div className="flex h-full flex-col items-center justify-center gap-1 text-center text-sm text-muted-foreground">
              <p className="font-semibold text-foreground">How can we help?</p>
              <p>Tell us what’s going on — a deposit, a withdrawal, a bet — and our team will reply here.</p>
            </div>
          ) : messages.map((m) => {
            const mine = !m.from_staff;
            return (
              <div key={m.id} className={`flex gap-2 ${mine ? 'flex-row-reverse' : ''}`}>
                <div className={`flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-xs font-bold ${mine ? 'bg-primary text-primary-foreground' : 'bg-secondary text-secondary-foreground'}`}>
                  {mine ? (user.username[0] ?? '?').toUpperCase() : <FaHeadset size={13} />}
                </div>
                <div className={`max-w-[78%] rounded-2xl px-4 py-2 text-sm ${mine ? 'rounded-tr-sm bg-primary text-primary-foreground' : 'rounded-tl-sm bg-muted'}`}>
                  {!mine && <p className="mb-0.5 text-xs font-semibold text-secondary">{m.sender} · Support</p>}
                  <p className="whitespace-pre-wrap break-words">{m.body}</p>
                  <p className={`mt-0.5 text-[10px] ${mine ? 'text-primary-foreground/70' : 'text-muted-foreground'}`}>
                    {new Date(m.created_at).toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                    {mine && (m.read ? ' · Seen' : ' · Sent')}
                  </p>
                </div>
              </div>
            );
          })}
        </div>

        {user && (
          <form onSubmit={send} className="border-t border-border p-3">
            {error && <p className="mb-2 text-xs font-semibold text-down">{error}</p>}
            <div className="flex gap-2">
              <Input value={text} onChange={(e) => setText(e.target.value)} placeholder="Write to support…" maxLength={1000} disabled={sending} />
              <button type="submit" disabled={sending || !text.trim()}
                className="flex items-center gap-1.5 rounded-md bg-primary px-4 py-2 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50">
                <FaPaperPlane size={12} /> Send
              </button>
            </div>
          </form>
        )}
      </Card>
    </div>
  );
}
