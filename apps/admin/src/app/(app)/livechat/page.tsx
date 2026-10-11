'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { BsPersonCircle, BsSearch, BsSendFill } from 'react-icons/bs';
import { FaRegCommentDots } from 'react-icons/fa';
import { Badge, Btn, EmptyState, PageHeader, TextInput, cx } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';

interface Thread {
  player_id: number; username: string; email: string; kyc_status: string | null; unread: number; messages: number;
  last_at: string; last_body: string; last_from_staff: boolean;
}
interface Message { id: number; body: string; from_staff: boolean; sender: string; created_at: string; read: boolean }
interface ThreadDetail { player: { id: number; username: string; email: string; kyc_status: string | null }; results: Message[] }

const ago = (iso: string) => {
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString();
};

/** Private support inbox: one conversation per player; players never see each other. */
export default function SupportInboxPage() {
  const [q, setQ] = useState('');
  const [search, setSearch] = useState('');
  const { data, refetch } = useApi<{ results: Thread[]; unread_threads: number }>(`/admin/support/${search ? `?q=${encodeURIComponent(search)}` : ''}`);
  const [open, setOpen] = useState<number | null>(null);

  useEffect(() => {
    const t = window.setInterval(() => { if (document.visibilityState === 'visible') refetch(); }, 8000);
    return () => window.clearInterval(t);
  }, [refetch]);

  const threads = data?.results ?? [];
  return (
    <div className="space-y-5">
      <PageHeader icon={FaRegCommentDots} eyebrow="Operations" title="Support chat"
        description="Private conversations with players — each player sees only their own chat with your team. Replies notify the player." />
      <div className="grid gap-5 lg:grid-cols-[340px_minmax(0,1fr)]">
        <div className="flex h-[calc(100vh-220px)] min-h-[420px] flex-col overflow-hidden rounded-2xl border border-border/70 bg-card">
          <form onSubmit={(e) => { e.preventDefault(); setSearch(q.trim()); }} className="flex gap-2 border-b border-border p-3">
            <TextInput value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a player" />
            <Btn type="submit" icon={BsSearch} aria-label="Search" />
          </form>
          <ul className="min-h-0 flex-1 divide-y divide-border overflow-y-auto">
            {threads.length === 0 && <li className="p-6 text-center text-sm text-muted-foreground">{search ? 'No conversations match.' : 'No conversations yet.'}</li>}
            {threads.map((t) => (
              <li key={t.player_id}>
                <button onClick={() => setOpen(t.player_id)}
                  className={cx('flex w-full items-start gap-3 px-4 py-3 text-left hover:bg-muted/50', open === t.player_id && 'bg-muted/70')}>
                  <BsPersonCircle className="mt-0.5 shrink-0 text-muted-foreground" size={20} />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-center gap-2">
                      <span className={cx('truncate', t.unread ? 'font-extrabold' : 'font-semibold')}>{t.username}</span>
                      <span className="ml-auto shrink-0 text-[11px] text-muted-foreground">{ago(t.last_at)}</span>
                    </span>
                    <span className={cx('block truncate text-xs', t.unread ? 'text-foreground' : 'text-muted-foreground')}>
                      {t.last_from_staff && 'You: '}{t.last_body}
                    </span>
                  </span>
                  {t.unread > 0 && <span className="mt-0.5 rounded-full bg-live px-1.5 text-[11px] font-bold text-white">{t.unread}</span>}
                </button>
              </li>
            ))}
          </ul>
        </div>
        {open ? <ThreadPane key={open} playerId={open} onChanged={refetch} /> : (
          <div className="flex items-center justify-center rounded-2xl border border-border/70 bg-card">
            <EmptyState icon={FaRegCommentDots} title="Pick a conversation">Unread conversations are in bold with a red count.</EmptyState>
          </div>
        )}
      </div>
    </div>
  );
}

function ThreadPane({ playerId, onChanged }: { playerId: number; onChanged: () => void }) {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<ThreadDetail>(`/admin/support/${playerId}/`);
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const count = data?.results.length ?? 0;

  const refresh = useCallback(() => { refetch(); onChanged(); }, [refetch, onChanged]);
  useEffect(() => { onChanged(); }, [data, onChanged]);  // opening marks it read
  useEffect(() => {
    const t = window.setInterval(() => { if (document.visibilityState === 'visible') refetch(); }, 4000);
    return () => window.clearInterval(t);
  }, [refetch]);
  useEffect(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight; }, [count]);

  async function send(e: React.FormEvent) {
    e.preventDefault();
    if (!accessToken || !text.trim()) return;
    setBusy(true); setError(null);
    const res = await authedPost(`/admin/support/${playerId}/`, { body: text.trim() }, accessToken);
    setBusy(false);
    if (res.error) { setError(res.error); return; }
    setText('');
    refresh();
  }

  const p = data?.player;
  return (
    <div className="flex h-[calc(100vh-220px)] min-h-[420px] flex-col overflow-hidden rounded-2xl border border-border/70 bg-card">
      <div className="flex flex-wrap items-center gap-3 border-b border-border px-4 py-3">
        <p className="font-bold">{p?.username ?? '…'}</p>
        {p?.kyc_status && <Badge tone={p.kyc_status === 'verified' ? 'green' : 'gold'}>KYC {p.kyc_status}</Badge>}
        <span className="text-xs text-muted-foreground">{p?.email}</span>
        <Link href={`/players/${playerId}`} className="ml-auto text-xs font-semibold text-secondary hover:underline">Player page — balance, tickets, withdrawals →</Link>
      </div>
      <div ref={box} className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
        {(data?.results ?? []).map((m) => (
          <div key={m.id} className={cx('flex', m.from_staff && 'justify-end')}>
            <div className={cx('max-w-[78%] rounded-2xl px-4 py-2 text-sm', m.from_staff ? 'rounded-tr-sm bg-secondary text-secondary-foreground' : 'rounded-tl-sm bg-muted')}>
              <p className={cx('mb-0.5 text-xs font-semibold', m.from_staff ? 'text-secondary-foreground/80' : 'text-muted-foreground')}>{m.sender}</p>
              <p className="whitespace-pre-wrap break-words">{m.body}</p>
              <p className={cx('mt-0.5 text-[10px]', m.from_staff ? 'text-secondary-foreground/70' : 'text-muted-foreground')}>
                {new Date(m.created_at).toLocaleString([], { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' })}
                {m.from_staff && (m.read ? ' · Seen' : ' · Sent')}
              </p>
            </div>
          </div>
        ))}
      </div>
      <form onSubmit={send} className="border-t border-border p-3">
        {error && <p className="mb-2 text-xs font-semibold text-live">{error}</p>}
        <div className="flex gap-2">
          <TextInput value={text} onChange={(e) => setText(e.target.value)} placeholder={`Reply to ${p?.username ?? 'the player'}…`} maxLength={1000} />
          <Btn type="submit" variant="primary" icon={BsSendFill} busy={busy} disabled={!text.trim()}>Send</Btn>
        </div>
      </form>
    </div>
  );
}
