'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { FaBullhorn, FaFlag, FaLock, FaPaperPlane, FaReply, FaThumbtack, FaTimes, FaUsers } from 'react-icons/fa';
import { Card } from '@slyk/ui/components/card';
import { Input } from '@slyk/ui/components/input';
import { Spinner } from '@slyk/ui/components/spinner';
import { useAuth } from '@/lib/auth-context';
import { authedGet, authedPost } from '@/lib/use-api';

interface Room {
  id: number; slug: string; name: string; description: string; audience: string; staff_only_posting: boolean;
  slow_mode_seconds: number; unread: number; last: { sender: string; body: string; at: string } | null;
}
interface Message {
  id: number; body: string; sender: string; role: 'player' | 'agent' | 'staff'; from_staff: boolean; mine: boolean;
  pinned: boolean; created_at: string; reply_to: { id: number; sender: string; body: string } | null;
}
interface Me { role: string; username: string; muted: boolean; muted_until: string | null }

const POLL_MS = 4000;
const ROLE_BADGE: Record<string, string> = {
  staff: 'bg-secondary/20 text-secondary', agent: 'bg-gold/20 text-gold',
};
const time = (iso: string) => new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });

/** Group chat: rooms for all players, a room for agents, and announcements from the team. */
export default function ChatPage() {
  const { user, accessToken } = useAuth();
  const [rooms, setRooms] = useState<Room[] | null>(null);
  const [me, setMe] = useState<Me | null>(null);
  const [slug, setSlug] = useState<string | null>(null);
  const [messages, setMessages] = useState<Message[]>([]);
  const [pinned, setPinned] = useState<Message[]>([]);
  const [hasMore, setHasMore] = useState(false);
  const [text, setText] = useState('');
  const [replyTo, setReplyTo] = useState<Message | null>(null);
  const [sending, setSending] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const lastId = useRef(0);
  const stick = useRef(true);
  const room = rooms?.find((r) => r.slug === slug) ?? null;

  const loadRooms = useCallback(async () => {
    if (!accessToken) return;
    const res = await authedGet<{ results: Room[]; me: Me }>('/chat/rooms/', accessToken);
    if (!res.data) return;
    setRooms(res.data.results); setMe(res.data.me);
    setSlug((s) => s ?? res.data!.results.find((r) => !r.staff_only_posting)?.slug ?? res.data!.results[0]?.slug ?? null);
  }, [accessToken]);

  // Open a room: its latest page and pinned messages.
  const openRoom = useCallback(async (s: string) => {
    if (!accessToken) return;
    const res = await authedGet<{ results: Message[]; pinned: Message[] | null; has_more: boolean }>(`/chat/rooms/${s}/messages/`, accessToken);
    if (!res.data) { setNotice(res.error ?? 'Could not open this room.'); return; }
    stick.current = true;
    setMessages(res.data.results); setPinned(res.data.pinned ?? []); setHasMore(res.data.has_more);
    lastId.current = res.data.results.at(-1)?.id ?? 0;
  }, [accessToken]);

  useEffect(() => { void loadRooms(); }, [loadRooms]);
  useEffect(() => { setMessages([]); setReplyTo(null); setNotice(null); lastId.current = 0; if (slug) void openRoom(slug); }, [slug, openRoom]);

  // New messages in the open room, and unread counts for the others.
  useEffect(() => {
    if (!accessToken || !slug) return;
    let tick = 0;
    const timer = window.setInterval(async () => {
      if (document.visibilityState !== 'visible') return;
      const res = await authedGet<{ results: Message[] }>(`/chat/rooms/${slug}/messages/?after=${lastId.current}`, accessToken);
      const fresh = res.data?.results ?? [];
      if (fresh.length > 0) {
        lastId.current = fresh.at(-1)!.id;
        setMessages((m) => [...m, ...fresh.filter((f) => !m.some((x) => x.id === f.id))]);
      }
      // Every 5th tick: re-read the room (hidden or deleted messages drop out) and the room list.
      if (++tick % 5 === 0) {
        void loadRooms();
        const full = await authedGet<{ results: Message[]; pinned: Message[] | null }>(`/chat/rooms/${slug}/messages/`, accessToken);
        if (full.data) {
          const live = new Set(full.data.results.map((m) => m.id));
          const oldest = full.data.results[0]?.id ?? 0;
          setMessages((m) => m.filter((x) => x.id < oldest || live.has(x.id)));
          setPinned(full.data.pinned ?? []);
        }
      }
    }, POLL_MS);
    return () => window.clearInterval(timer);
  }, [accessToken, slug, loadRooms]);

  // Keep the newest message in view unless the player scrolled up to read.
  useEffect(() => { if (stick.current && box.current) box.current.scrollTop = box.current.scrollHeight; }, [messages]);

  async function older() {
    if (!accessToken || !slug || messages.length === 0) return;
    const res = await authedGet<{ results: Message[] }>(`/chat/rooms/${slug}/messages/?before=${messages[0].id}`, accessToken);
    const page = res.data?.results ?? [];
    stick.current = false;
    setMessages((m) => [...page, ...m]);
    setHasMore(page.length >= 50);
  }

  async function send(e: React.FormEvent) {
    e.preventDefault();
    const body = text.trim();
    if (!body || !accessToken || !slug) return;
    setSending(true); setNotice(null);
    const res = await authedPost<Message>(`/chat/rooms/${slug}/messages/`, { body, reply_to: replyTo?.id }, accessToken);
    setSending(false);
    if (res.error || !res.data) { setNotice(res.error ?? 'Could not send.'); return; }
    stick.current = true;
    lastId.current = Math.max(lastId.current, res.data.id);
    setMessages((m) => [...m, res.data!]);
    setText(''); setReplyTo(null);
  }

  async function report(m: Message) {
    if (!accessToken || !window.confirm('Report this message to the BetBlits team?')) return;
    const res = await authedPost(`/chat/messages/${m.id}/report/`, {}, accessToken);
    setNotice(res.error ?? 'Thanks — our team will take a look.');
  }

  if (!user) {
    return (
      <Card className="mx-auto max-w-md space-y-3 rounded-2xl p-8 text-center">
        <FaUsers className="mx-auto text-secondary" size={28} />
        <p className="text-lg font-extrabold">Community chat</p>
        <p className="text-sm text-muted-foreground">Log in to chat with other players and get news from the team.</p>
        <Link href="/login?next=/chat" className="inline-block rounded-xl bg-win px-5 py-2.5 text-sm font-extrabold text-win-foreground">Log in</Link>
      </Card>
    );
  }

  const cannotPost = room?.staff_only_posting ? 'Only the BetBlits team posts here.'
    : me?.muted ? `You can’t post in chat${me.muted_until ? ` until ${new Date(me.muted_until).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}` : ''}.`
      : null;

  return (
    <div className="mx-auto flex h-[calc(100dvh-11rem)] min-h-[420px] max-w-5xl flex-col gap-3 md:flex-row">
      {/* Rooms: a scrolling strip on phones, a rail on wider screens */}
      <nav aria-label="Chat rooms" className="flex shrink-0 gap-2 overflow-x-auto md:w-56 md:flex-col md:overflow-visible">
        {rooms === null && <div className="h-12 w-full animate-pulse rounded-xl bg-muted" />}
        {rooms?.map((r) => (
          <button key={r.slug} onClick={() => setSlug(r.slug)}
            className={`flex min-w-[9.5rem] shrink-0 items-center gap-2 rounded-xl border px-3 py-2.5 text-left transition-colors md:min-w-0 ${
              r.slug === slug ? 'border-secondary bg-secondary/15' : 'border-border bg-card hover:bg-muted'}`}>
            <span className="text-muted-foreground">{r.staff_only_posting ? <FaBullhorn size={13} /> : r.audience === 'agents' ? <FaLock size={12} /> : <FaUsers size={13} />}</span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-bold">{r.name}</span>
              <span className="hidden truncate text-[11px] text-muted-foreground md:block">{r.last ? `${r.last.sender}: ${r.last.body}` : r.description}</span>
            </span>
            {r.unread > 0 && r.slug !== slug && (
              <span className="rounded-full bg-live px-1.5 py-px text-[10px] font-bold text-white">{r.unread > 99 ? '99+' : r.unread}</span>
            )}
          </button>
        ))}
      </nav>

      <Card className="flex min-h-0 flex-1 flex-col overflow-hidden rounded-2xl p-0">
        <header className="border-b border-border px-4 py-3">
          <p className="font-extrabold">{room?.name ?? 'Chat'}</p>
          <p className="text-xs text-muted-foreground">{room?.description}</p>
        </header>
        {pinned.length > 0 && (
          <div className="space-y-1 border-b border-border bg-gold/10 px-4 py-2">
            {pinned.map((m) => (
              <p key={m.id} className="flex items-start gap-2 text-xs"><FaThumbtack className="mt-0.5 shrink-0 text-gold" size={10} />
                <span><b>{m.sender}:</b> {m.body}</span></p>
            ))}
          </div>
        )}
        <div ref={box} className="min-h-0 flex-1 space-y-2.5 overflow-y-auto px-3 py-3 sm:px-4"
          onScroll={(e) => { const el = e.currentTarget; stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80; }}>
          {hasMore && <button onClick={older} className="mx-auto block rounded-full border border-border px-3 py-1 text-xs font-semibold text-muted-foreground hover:bg-muted">Earlier messages</button>}
          {messages.length === 0 && <p className="py-10 text-center text-sm text-muted-foreground">No messages yet{room && !room.staff_only_posting ? ' — say hello.' : '.'}</p>}
          {messages.map((m) => (
            <div key={m.id} className={`group flex ${m.mine ? 'justify-end' : 'justify-start'}`}>
              <div className={`max-w-[85%] rounded-2xl px-3 py-2 text-sm sm:max-w-[70%] ${m.mine ? 'bg-secondary text-secondary-foreground' : m.from_staff ? 'border border-secondary/40 bg-secondary/10' : 'bg-muted'}`}>
                {!m.mine && (
                  <p className="mb-0.5 flex items-center gap-1.5 text-[11px] font-bold">
                    {m.sender}
                    {ROLE_BADGE[m.role] && <span className={`rounded px-1 py-px text-[9px] uppercase tracking-wide ${ROLE_BADGE[m.role]}`}>{m.role === 'staff' ? 'Team' : 'Agent'}</span>}
                  </p>
                )}
                {m.reply_to && (
                  <p className="mb-1 truncate rounded-lg bg-black/10 px-2 py-1 text-[11px] opacity-80">
                    <b>{m.reply_to.sender}:</b> {m.reply_to.body || 'message removed'}
                  </p>
                )}
                <p className="whitespace-pre-wrap break-words">{m.body}</p>
                <p className="mt-0.5 flex items-center justify-end gap-2 text-[10px] opacity-60">
                  {!room?.staff_only_posting && !me?.muted && (
                    <button onClick={() => setReplyTo(m)} aria-label="Reply" className="opacity-0 transition-opacity focus:opacity-100 group-hover:opacity-100"><FaReply size={10} /></button>
                  )}
                  {!m.mine && !m.from_staff && (
                    <button onClick={() => report(m)} aria-label="Report this message" className="opacity-0 transition-opacity focus:opacity-100 group-hover:opacity-100"><FaFlag size={10} /></button>
                  )}
                  {time(m.created_at)}
                </p>
              </div>
            </div>
          ))}
        </div>
        {notice && <p role="status" className="border-t border-border bg-muted/50 px-4 py-2 text-xs text-muted-foreground">{notice}</p>}
        {cannotPost ? (
          <p className="border-t border-border px-4 py-3 text-center text-xs text-muted-foreground">{cannotPost}</p>
        ) : (
          <form onSubmit={send} className="border-t border-border p-2.5 sm:p-3">
            {replyTo && (
              <p className="mb-2 flex items-center gap-2 rounded-lg bg-muted px-2.5 py-1.5 text-xs">
                <FaReply size={10} className="shrink-0 text-muted-foreground" />
                <span className="min-w-0 flex-1 truncate">Replying to <b>{replyTo.sender}</b>: {replyTo.body}</span>
                <button type="button" onClick={() => setReplyTo(null)} aria-label="Cancel reply"><FaTimes size={11} /></button>
              </p>
            )}
            <div className="flex gap-2">
              <Input value={text} onChange={(e) => setText(e.target.value)} maxLength={500} placeholder={`Message ${room?.name ?? ''}`} aria-label="Message" className="h-11 flex-1" />
              <button type="submit" disabled={sending || !text.trim()} aria-label="Send"
                className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-win text-win-foreground disabled:opacity-50">
                {sending ? <Spinner size={14} /> : <FaPaperPlane size={14} />}
              </button>
            </div>
            <p className="mt-1.5 text-[10px] text-muted-foreground">Be respectful. Never share phone numbers, passwords or payment details — the team will never ask for them here.</p>
          </form>
        )}
      </Card>
    </div>
  );
}
