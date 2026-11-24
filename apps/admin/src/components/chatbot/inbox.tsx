'use client';

import { useEffect, useRef, useState } from 'react';
import { BsCheck2, BsCheck2All, BsExclamationTriangleFill, BsSearch, BsSend } from 'react-icons/bs';
import { Badge, Btn, Field, Notice, Panel, TextInput, cx } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';
import { authedUpload } from '@/lib/upload';
import { AttachPicker, AuthedMedia } from '@/components/chat/attachments';

interface Conversation {
  address: string; player: string | null; incoming: number; outgoing: number; last_at: string; last_text: string;
  last_direction: 'in' | 'out'; unanswered: boolean; failed: number; can_reply: boolean;
}
interface Message {
  id: string; direction: 'in' | 'out'; text: string; at: string; buttons?: string[]; media?: { kind: string; url: string } | null; status?: 'queued' | 'sent' | 'delivered' | 'read' | 'failed';
  status_label?: string; error?: string; error_code?: string; source?: 'bot' | 'staff' | 'test'; sent_by?: string;
}
interface Thread { address: string; player: string | null; messages: Message[]; can_reply: boolean; window_ends: string | null }
interface Health {
  configured: boolean; problem: string; incoming_24h: number; outgoing_24h: number; by_status: Record<string, number>;
  failures: { error: string; code: string; count: number; last_at: string }[]; last_incoming_at: string | null; last_outgoing_at: string | null;
}

const ago = (iso: string | null) => {
  if (!iso) return 'never';
  const s = Math.max(0, Math.round((Date.now() - Date.parse(iso)) / 1000));
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return `${Math.floor(s / 86400)} d ago`;
};
const clock = (iso: string) => new Date(iso).toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
const pretty = (n: string) => (n.length > 6 ? `+${n.slice(0, n.length - 9)} ${n.slice(-9, -7)} ${n.slice(-7, -4)} ${n.slice(-4)}` : n);

function Ticks({ m }: { m: Message }) {
  if (m.status === 'failed') return <BsExclamationTriangleFill className="text-live" size={11} aria-label="Failed" />;
  if (m.status === 'read') return <BsCheck2All className="text-sky-400" size={14} aria-label="Read" />;
  if (m.status === 'delivered') return <BsCheck2All className="text-muted-foreground" size={14} aria-label="Delivered" />;
  if (m.status === 'sent') return <BsCheck2 className="text-muted-foreground" size={14} aria-label="Sent" />;
  return <span className="text-[10px] text-muted-foreground">sending…</span>;
}

/** Delivery health: says in plain words whether sending works, what Meta refused and why, and can send a test. */
export function DeliveryHealth() {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<Health>('/admin/chatbot/health/');
  const [to, setTo] = useState('');
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<{ ok: boolean; text: string } | null>(null);
  useEffect(() => { const t = window.setInterval(refetch, 15000); return () => window.clearInterval(t); }, [refetch]);
  if (!data) return null;

  async function test() {
    if (!accessToken) return;
    setBusy(true); setResult(null);
    const res = await authedPost<{ ok: boolean; error: string; via: string }>('/admin/chatbot/health/', { to }, accessToken);
    setBusy(false);
    if (res.error) setResult({ ok: false, text: res.error });
    else if (res.data) setResult({ ok: res.data.ok, text: res.data.ok
      ? `Sent${res.data.via === 'template' ? ' (as the “hello_world” template: this number hasn’t written in the last 24 hours)' : ''}. Check the phone.`
      : res.data.error || 'Meta refused it.' });
    refetch();
  }
  const s = data.by_status;
  return (
    <Panel title="Delivery health"
      actions={data.problem ? <Badge tone="red" dot>Replies not going out</Badge> : data.configured ? <Badge tone="green" dot>Working</Badge> : <Badge tone="red" dot>Not connected</Badge>}>
      {data.problem && <div className="mb-4"><Notice tone="red">{data.problem}</Notice></div>}
      <div className="grid gap-3 sm:grid-cols-5">
        {([['Received (24h)', data.incoming_24h], ['Sent (24h)', data.outgoing_24h], ['Delivered / read', (s.delivered ?? 0) + (s.read ?? 0)],
          ['Failed', s.failed ?? 0], ['Last message in', ago(data.last_incoming_at)]] as [string, string | number][]).map(([k, v]) => (
          <div key={k} className="rounded-xl border border-border bg-card p-3">
            <p className="text-xs text-muted-foreground">{k}</p>
            <p className={cx('mt-0.5 text-lg font-bold tabular-nums', k === 'Failed' && Number(v) > 0 && 'text-live')}>{v}</p>
          </div>
        ))}
      </div>
      {data.failures.length > 0 && (
        <ul className="mt-4 space-y-1.5 text-sm">
          {data.failures.map((f, i) => (
            <li key={i} className="flex flex-wrap items-baseline gap-2 rounded-lg bg-live/10 px-3 py-2">
              <span className="font-bold tabular-nums">{f.count}×</span><span className="min-w-0 flex-1">{f.error}</span>
              <span className="text-xs text-muted-foreground">{f.code && `code ${f.code} · `}{ago(f.last_at)}</span>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-4 flex flex-wrap items-end gap-3">
        <Field label="Send a test message to" className="w-64" hint="With country code, e.g. 263771234567">
          <TextInput inputMode="tel" value={to} onChange={(e) => setTo(e.target.value)} placeholder="263771234567" />
        </Field>
        <Btn busy={busy} disabled={to.replace(/\D/g, '').length < 8} onClick={test}>Send test</Btn>
        {result && <span className={cx('text-sm', result.ok ? 'text-win' : 'text-live')}>{result.ok ? '✓' : '✗'} {result.text}</span>}
      </div>
    </Panel>
  );
}

/** The conversations: who wrote, what the bot (or staff) answered, and whether each message arrived and was read. */
export function Inbox() {
  const { accessToken } = useAuth();
  const [q, setQ] = useState('');
  const { data: list, refetch: refetchList } = useApi<{ conversations: Conversation[] }>(`/admin/chatbot/inbox/${q ? `?q=${encodeURIComponent(q)}` : ''}`);
  const [open, setOpen] = useState<string | null>(null);
  const { data: thread, refetch: refetchThread } = useApi<Thread>(open ? `/admin/chatbot/inbox/${open}/` : null);
  const [text, setText] = useState('');
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  const bottom = useRef<HTMLDivElement>(null);
  useEffect(() => { const t = window.setInterval(() => { refetchList(); if (open) refetchThread(); }, 8000); return () => window.clearInterval(t); }, [open, refetchList, refetchThread]);
  useEffect(() => { bottom.current?.scrollIntoView({ block: 'end' }); }, [thread?.messages.length, open]);

  async function send() {
    if (!accessToken || !open) return;
    setBusy(true); setNotice(null);
    let res;
    if (file) {
      const form = new FormData();
      form.append('file', file);
      form.append('text', text);
      res = await authedUpload<Thread>(`/admin/chatbot/inbox/${open}/`, form, accessToken);
    } else {
      res = await authedPost<Thread>(`/admin/chatbot/inbox/${open}/`, { text }, accessToken);
    }
    setBusy(false);
    if (res.error) { setNotice({ tone: 'red', text: res.error }); return; }
    setText(''); setFile(null);
    refetchThread(); refetchList();
  }

  const convs = list?.conversations ?? [];
  return (
    <div className="grid min-h-[560px] gap-4 lg:grid-cols-[320px_1fr]">
      <div className="flex min-h-0 flex-col rounded-2xl border border-border/70 bg-card">
        <div className="relative border-b border-border/60 p-3">
          <BsSearch className="pointer-events-none absolute left-6 top-1/2 -translate-y-1/2 text-muted-foreground" size={13} />
          <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Find a number" inputMode="tel"
            className="h-9 w-full rounded-lg border border-border bg-input/60 pl-8 pr-3 text-sm outline-none focus:border-secondary" />
        </div>
        <ul className="max-h-[640px] flex-1 divide-y divide-border/50 overflow-y-auto">
          {convs.length === 0 && <li className="p-6 text-center text-sm text-muted-foreground">No conversations yet. They appear here when someone messages the bot.</li>}
          {convs.map((c) => (
            <li key={c.address}>
              <button onClick={() => { setOpen(c.address); setNotice(null); }}
                className={cx('w-full px-4 py-3 text-left hover:bg-muted/40', open === c.address && 'bg-muted/50')}>
                <div className="flex items-center justify-between gap-2">
                  <span className="truncate font-semibold">{c.player ?? pretty(c.address)}</span>
                  <span className="shrink-0 text-[11px] text-muted-foreground">{ago(c.last_at)}</span>
                </div>
                {c.player && <p className="text-[11px] text-muted-foreground">{pretty(c.address)}</p>}
                <p className="mt-0.5 truncate text-xs text-muted-foreground">{c.last_direction === 'out' ? '↩ ' : ''}{c.last_text.replace(/\s+/g, ' ')}</p>
                <div className="mt-1 flex gap-1.5">
                  {c.unanswered && <Badge tone="gold">Unanswered</Badge>}
                  {c.failed > 0 && <Badge tone="red">{c.failed} failed</Badge>}
                </div>
              </button>
            </li>
          ))}
        </ul>
      </div>

      <div className="flex min-h-0 flex-col rounded-2xl border border-border/70 bg-card">
        {!open ? (
          <div className="flex flex-1 items-center justify-center p-10 text-sm text-muted-foreground">Choose a conversation.</div>
        ) : !thread ? (
          <div className="flex-1 animate-pulse bg-muted/20" />
        ) : (
          <>
            <div className="border-b border-border/60 px-4 py-3">
              <p className="font-bold">{thread.player ?? pretty(thread.address)}</p>
              <p className="text-xs text-muted-foreground">
                {pretty(thread.address)} · {thread.can_reply ? `you can reply until ${new Date(thread.window_ends!).toLocaleString()}` : 'the 24-hour reply window is closed: they need to message first'}
              </p>
            </div>
            <div className="max-h-[480px] flex-1 space-y-2 overflow-y-auto bg-muted/10 p-4">
              {thread.messages.map((m) => (
                <div key={m.id} className={cx('flex', m.direction === 'out' ? 'justify-end' : 'justify-start')}>
                  <div className={cx('max-w-[78%] rounded-2xl px-3 py-2 text-sm',
                    m.direction === 'out' ? (m.status === 'failed' ? 'bg-live/15 ring-1 ring-live/40' : 'bg-secondary/20') : 'bg-card ring-1 ring-border')}>
                    {m.media && <div className="mb-1.5"><AuthedMedia url={m.media.url} kind={m.media.kind} token={accessToken} /></div>}
                    {m.text && <p className="whitespace-pre-wrap break-words">{m.text}</p>}
                    {m.buttons && m.buttons.length > 0 && (
                      <div className="mt-1.5 flex flex-wrap gap-1">{m.buttons.map((b, i) => <span key={i} className="rounded-full border border-border px-2 py-0.5 text-[11px]">{b}</span>)}</div>
                    )}
                    <div className="mt-1 flex items-center justify-end gap-1.5 text-[10px] text-muted-foreground">
                      {m.direction === 'out' && m.source !== 'bot' && <span>{m.source === 'staff' ? `by ${m.sent_by}` : 'test'}</span>}
                      <span>{clock(m.at)}</span>
                      {m.direction === 'out' && <Ticks m={m} />}
                    </div>
                    {m.status === 'failed' && m.error && <p className="mt-1 text-[11px] font-semibold text-live">Not delivered: {m.error}</p>}
                  </div>
                </div>
              ))}
              <div ref={bottom} />
            </div>
            <div className="space-y-2 border-t border-border/60 p-3">
              {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}
              <div className="flex gap-2">
                <AttachPicker file={file} onChange={setFile} disabled={!thread.can_reply} onError={(t) => setNotice({ tone: 'red', text: t })} />
                <textarea value={text} onChange={(e) => setText(e.target.value)} rows={2} maxLength={1000} disabled={!thread.can_reply}
                  placeholder={thread.can_reply ? (file ? 'Add a caption (optional)…' : 'Write a reply as support…') : 'Replies are blocked until they message again.'}
                  onKeyDown={(e) => { if (e.key === 'Enter' && (e.metaKey || e.ctrlKey) && (text.trim() || file)) void send(); }}
                  className="min-h-[44px] flex-1 resize-none rounded-xl border border-border bg-input/60 px-3 py-2 text-sm outline-none focus:border-secondary disabled:opacity-60" />
                <Btn variant="primary" icon={BsSend} busy={busy} disabled={(!text.trim() && !file) || !thread.can_reply} onClick={send}>Send</Btn>
              </div>
              <p className="text-[11px] text-muted-foreground">Staff replies are logged. Players see them as coming from the same number as the bot.</p>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
