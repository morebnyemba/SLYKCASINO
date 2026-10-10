'use client';

import { useEffect, useRef, useState } from 'react';
import { BsCloudRainHeavyFill, BsSendFill, BsTrophyFill, BsXLg } from 'react-icons/bs';
import type { ChatMessage } from '@/lib/jet';

/** The game's chat lobby: players, big-win shout-outs and rain drops. */
export function ChatPanel({ messages, enabled, loggedIn, onSend, onClose }: {
  messages: ChatMessage[];
  enabled: boolean;
  loggedIn: boolean;
  onSend: (body: string) => Promise<{ error?: string }>;
  onClose?: () => void;
}) {
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const list = useRef<HTMLDivElement>(null);
  const stick = useRef(true);

  // Follow new messages unless the player has scrolled up to read.
  useEffect(() => {
    const el = list.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [messages]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const body = text.trim();
    if (!body || busy) return;
    setBusy(true); setError(null);
    const res = await onSend(body);
    setBusy(false);
    if (res.error) setError(res.error);
    else { setText(''); stick.current = true; }
  }

  return (
    <section className="flex h-full min-h-0 flex-col rounded-2xl border border-[#2c2d30] bg-[#1b1c1d] text-white">
      <header className="flex items-center gap-2 border-b border-[#2c2d30] px-4 py-2.5">
        <span className="h-2 w-2 rounded-full bg-[#28a909] shadow-[0_0_8px_#28a909]" />
        <h2 className="flex-1 text-sm font-extrabold">Chat</h2>
        {onClose && (
          <button onClick={onClose} aria-label="Close chat" className="rounded-lg p-1.5 text-white/60 hover:bg-white/10"><BsXLg size={12} /></button>
        )}
      </header>
      <div
        ref={list}
        onScroll={(e) => { const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 40; }}
        className="min-h-0 flex-1 space-y-1.5 overflow-y-auto overscroll-contain px-3 py-3"
      >
        {!enabled && <p className="py-6 text-center text-xs text-white/40">Chat is switched off right now.</p>}
        {enabled && messages.length === 0 && <p className="py-6 text-center text-xs text-white/40">Say hi — nobody’s talking yet.</p>}
        {messages.map((m) => <Message key={m.id} m={m} />)}
      </div>
      {enabled && (
        <form onSubmit={send} className="border-t border-[#2c2d30] p-2.5">
          {error && <p className="mb-1.5 px-1 text-[11px] font-semibold text-[#f87171]">{error}</p>}
          {loggedIn ? (
            <div className="flex items-center gap-2 rounded-full bg-[#141516] py-1 pl-4 pr-1">
              <input
                value={text} maxLength={160} onChange={(e) => setText(e.target.value)} placeholder="Reply…" aria-label="Chat message"
                className="min-w-0 flex-1 bg-transparent text-sm outline-none placeholder:text-white/30"
              />
              <button type="submit" disabled={busy || !text.trim()} aria-label="Send"
                className="flex h-8 w-8 items-center justify-center rounded-full bg-[#28a909] text-white disabled:opacity-40">
                <BsSendFill size={12} />
              </button>
            </div>
          ) : (
            <a href="/login" target="_top" className="block rounded-full bg-[#141516] py-2 text-center text-xs font-bold text-[#28a909]">Log in to chat</a>
          )}
        </form>
      )}
    </section>
  );
}

function Message({ m }: { m: ChatMessage }) {
  const time = new Date(m.at).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
  if (m.kind === 'win' || m.kind === 'rain' || m.kind === 'system') {
    const rain = m.kind === 'rain';
    return (
      <div className={`rounded-xl border px-3 py-2 text-xs leading-snug ${
        rain ? 'border-[#34b4ff]/40 bg-[#34b4ff]/10' : 'border-[#f5b400]/40 bg-[#f5b400]/10'
      }`}>
        <p className={`mb-0.5 flex items-center gap-1.5 text-[11px] font-extrabold ${rain ? 'text-[#34b4ff]' : 'text-[#f5b400]'}`}>
          {rain ? <BsCloudRainHeavyFill size={11} /> : <BsTrophyFill size={11} />} {m.name}
          <span className="ml-auto font-semibold text-white/30">{time}</span>
        </p>
        <p className="break-words text-white/90">{m.body}</p>
      </div>
    );
  }
  return (
    <div className="rounded-xl bg-[#101011] px-3 py-1.5 text-xs leading-snug">
      <p className="flex items-center text-[11px] font-bold text-white/50">
        {m.name}<span className="ml-auto font-semibold text-white/25">{time}</span>
      </p>
      <p className="break-words text-white/90">{m.body}</p>
    </div>
  );
}
