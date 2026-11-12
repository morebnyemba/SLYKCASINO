'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { BsChatSquareText, BsEyeSlash, BsFlag, BsPinAngle, BsTrash, BsVolumeMute } from 'react-icons/bs';
import {
  Badge, Btn, Drawer, EmptyState, Field, Notice, PageHeader, Panel, Select, Switch, TextInput, cx,
} from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost, authedRequest, useApi } from '@/lib/use-api';

interface Room {
  id: number; slug: string; name: string; description: string; audience: string; audience_label: string;
  staff_only_posting: boolean; is_open: boolean; slow_mode_seconds: number; sort_order: number;
  total: number; hidden: number; reported: number; last: { sender: string; body: string; at: string } | null;
}
interface Message {
  id: number; body: string; sender: string; role: string; from_staff: boolean; pinned: boolean; created_at: string;
  player_id: number | null; hidden: boolean; hidden_by: string; hidden_reason: string; reports: number;
  reply_to: { id: number; sender: string; body: string } | null;
}
interface Mute { player_id: number; username: string; reason: string; until: string | null; muted_by: string }
interface RoomsResponse { results: Room[]; mutes: Mute[]; audiences: { id: string; label: string }[] }
type Only = '' | 'hidden' | 'reported';
type Tone = { tone: 'green' | 'red'; text: string } | null;

const POLL_MS = 5000;
const MUTE_OPTIONS = [['60', '1 hour'], ['1440', '1 day'], ['10080', '7 days'], ['', 'Until lifted']] as const;

/** Group chat moderation: every room, everything said in it (hidden messages too), and who is muted. */
export default function ChatModerationPage() {
  const { accessToken, user } = useAuth();
  const { data, refetch } = useApi<RoomsResponse>('/admin/chat/rooms/');
  const [roomId, setRoomId] = useState<number | null>(null);
  const [only, setOnly] = useState<Only>('');
  const [messages, setMessages] = useState<Message[]>([]);
  const [picked, setPicked] = useState<Set<number>>(new Set());
  const [text, setText] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Tone>(null);
  const [editing, setEditing] = useState<Room | 'new' | null>(null);
  const [muting, setMuting] = useState<Message | null>(null);
  const box = useRef<HTMLDivElement>(null);
  const rooms = data?.results ?? [];
  const room = rooms.find((r) => r.id === roomId) ?? null;

  useEffect(() => { if (roomId === null && rooms.length > 0) setRoomId(rooms.find((r) => r.slug === 'community')?.id ?? rooms[0].id); }, [rooms, roomId]);

  const load = useCallback(async (scroll = false) => {
    if (!accessToken || roomId === null) return;
    const res = await authedRequest<{ results: Message[] }>('GET', `/admin/chat/rooms/${roomId}/messages/${only ? `?only=${only}` : ''}`, accessToken);
    if (!res.data) return;
    setMessages(res.data.results);
    if (scroll) window.setTimeout(() => { if (box.current) box.current.scrollTop = box.current.scrollHeight; }, 0);
  }, [accessToken, roomId, only]);

  useEffect(() => { setPicked(new Set()); void load(true); }, [load]);
  useEffect(() => {
    const t = window.setInterval(() => { if (document.visibilityState === 'visible') { void load(); refetch(); } }, POLL_MS);
    return () => window.clearInterval(t);
  }, [load, refetch]);

  async function moderate(ids: number[], action: 'hide' | 'unhide' | 'delete' | 'pin' | 'unpin') {
    if (!accessToken || ids.length === 0) return;
    let reason = '';
    if (action === 'hide') {
      const typed = window.prompt(`Hide ${ids.length === 1 ? 'this message' : `${ids.length} messages`} from players? You can add a reason (optional).`, '');
      if (typed === null) return;
      reason = typed;
    }
    if (action === 'delete' && !window.confirm(`Delete ${ids.length === 1 ? 'this message' : `${ids.length} messages`} for good? This can’t be undone. (Hide instead if you may need it later.)`)) return;
    setBusy(true);
    const res = await authedPost<{ done: number }>('/admin/chat/moderate/', { ids, action, reason }, accessToken);
    setBusy(false);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: `${res.data?.done ?? 0} message${res.data?.done === 1 ? '' : 's'} ${{ hide: 'hidden', unhide: 'shown again', delete: 'deleted', pin: 'pinned', unpin: 'unpinned' }[action]}.` });
    setPicked(new Set());
    void load(); refetch();
  }

  async function post(e: React.FormEvent) {
    e.preventDefault();
    if (!accessToken || roomId === null || !text.trim()) return;
    setBusy(true);
    const res = await authedPost(`/admin/chat/rooms/${roomId}/messages/`, { body: text }, accessToken);
    setBusy(false);
    if (res.error) { setNotice({ tone: 'red', text: res.error }); return; }
    setText(''); void load(true);
  }

  async function unmute(m: Mute) {
    if (!accessToken) return;
    const res = await authedRequest('DELETE', `/admin/chat/mutes/${m.player_id}/`, accessToken);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: `${m.username} can post again.` });
    refetch();
  }

  const toggle = (id: number) => setPicked((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const pickedHidden = messages.filter((m) => picked.has(m.id) && m.hidden).map((m) => m.id);
  const pickedShown = messages.filter((m) => picked.has(m.id) && !m.hidden).map((m) => m.id);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3 [&>div:first-child]:mb-0">
        <PageHeader icon={BsChatSquareText} eyebrow="Operations" title="Community chat"
          description="Group rooms for players, agents and the team. Hide a message to take it out of players’ view (you can show it again); delete removes it for good. Mute stops a player posting; they can still read." />
        <Btn variant="primary" onClick={() => setEditing('new')}>+ New room</Btn>
      </div>
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}

      <div className="grid gap-4 lg:grid-cols-[260px_1fr]">
        <div className="space-y-2">
          {rooms.map((r) => (
            <button key={r.id} onClick={() => { setRoomId(r.id); setOnly(''); }}
              className={cx('w-full rounded-xl border p-3 text-left transition-colors', r.id === roomId ? 'border-secondary bg-secondary/10' : 'border-border/70 bg-card hover:bg-muted/40')}>
              <div className="flex items-center justify-between gap-2">
                <span className="truncate font-bold">{r.name}</span>
                {!r.is_open && <Badge tone="slate">Closed</Badge>}
              </div>
              <p className="text-xs text-muted-foreground">{r.audience_label}{r.staff_only_posting ? ' · team posts only' : ''}</p>
              <p className="mt-1 flex flex-wrap gap-x-3 text-[11px] text-muted-foreground">
                <span>{r.total} messages</span>
                {r.hidden > 0 && <span>{r.hidden} hidden</span>}
                {r.reported > 0 && <span className="font-bold text-live">{r.reported} reported</span>}
              </p>
            </button>
          ))}
        </div>

        <Panel
          title={room?.name ?? 'Room'}
          description={room ? `${room.description || room.audience_label}${room.slow_mode_seconds ? ` · slow mode ${room.slow_mode_seconds}s` : ''}` : undefined}
          actions={room && <Btn size="sm" onClick={() => setEditing(room)}>Room settings</Btn>}
          padded={false}
        >
          <div className="flex flex-wrap items-center gap-2 border-b border-border/60 px-4 py-2.5">
            {(['', 'reported', 'hidden'] as Only[]).map((o) => (
              <button key={o || 'all'} onClick={() => setOnly(o)}
                className={cx('rounded-full px-3 py-1 text-xs font-semibold', only === o ? 'bg-secondary text-secondary-foreground' : 'bg-muted text-muted-foreground hover:text-foreground')}>
                {o === '' ? 'All messages' : o === 'reported' ? `Reported${room?.reported ? ` (${room.reported})` : ''}` : `Hidden${room?.hidden ? ` (${room.hidden})` : ''}`}
              </button>
            ))}
            <span className="flex-1" />
            {picked.size > 0 && (
              <>
                <span className="text-xs font-semibold">{picked.size} selected</span>
                {pickedShown.length > 0 && <Btn size="sm" icon={BsEyeSlash} busy={busy} onClick={() => moderate(pickedShown, 'hide')}>Hide</Btn>}
                {pickedHidden.length > 0 && <Btn size="sm" busy={busy} onClick={() => moderate(pickedHidden, 'unhide')}>Show again</Btn>}
                <Btn size="sm" variant="danger" icon={BsTrash} busy={busy} onClick={() => moderate([...picked], 'delete')}>Delete</Btn>
              </>
            )}
          </div>

          <div ref={box} className="max-h-[56vh] min-h-[280px] space-y-1 overflow-y-auto px-2 py-2">
            {messages.length === 0 ? <EmptyState icon={BsChatSquareText} title={only ? 'Nothing here' : 'No messages yet'} /> : messages.map((m) => (
              <div key={m.id} className={cx('group flex items-start gap-2.5 rounded-xl px-2 py-2', m.hidden ? 'bg-live/5 opacity-70' : picked.has(m.id) ? 'bg-secondary/10' : 'hover:bg-muted/40')}>
                <input type="checkbox" checked={picked.has(m.id)} onChange={() => toggle(m.id)} aria-label={`Select message from ${m.sender}`} className="mt-1 h-4 w-4 shrink-0 cursor-pointer" />
                <div className="min-w-0 flex-1">
                  <p className="flex flex-wrap items-center gap-x-2 gap-y-0.5 text-xs">
                    {m.player_id && !m.from_staff
                      ? <Link href={`/players/${m.player_id}`} className="font-bold hover:underline">{m.sender}</Link>
                      : <span className="font-bold">{m.sender}</span>}
                    {m.role !== 'player' && <Badge tone={m.role === 'staff' ? 'indigo' : 'gold'}>{m.role === 'staff' ? 'Team' : 'Agent'}</Badge>}
                    {m.pinned && <Badge tone="gold">Pinned</Badge>}
                    {m.hidden && <Badge tone="red">Hidden by {m.hidden_by}{m.hidden_reason ? `: ${m.hidden_reason}` : ''}</Badge>}
                    {m.reports > 0 && <Badge tone="red"><BsFlag className="mr-1 inline" size={9} />{m.reports} report{m.reports === 1 ? '' : 's'}</Badge>}
                    <span className="text-muted-foreground">{new Date(m.created_at).toLocaleString([], { dateStyle: 'short', timeStyle: 'short' })}</span>
                  </p>
                  {m.reply_to && <p className="mt-0.5 truncate text-[11px] text-muted-foreground">↳ {m.reply_to.sender}: {m.reply_to.body}</p>}
                  <p className="mt-0.5 whitespace-pre-wrap break-words text-sm">{m.body}</p>
                </div>
                <div className="flex shrink-0 gap-1 opacity-0 transition-opacity focus-within:opacity-100 group-hover:opacity-100">
                  {m.hidden
                    ? <Btn size="sm" onClick={() => moderate([m.id], 'unhide')}>Show</Btn>
                    : <Btn size="sm" icon={BsEyeSlash} onClick={() => moderate([m.id], 'hide')} title="Hide from players">Hide</Btn>}
                  {!m.hidden && <Btn size="sm" icon={BsPinAngle} onClick={() => moderate([m.id], m.pinned ? 'unpin' : 'pin')}>{m.pinned ? 'Unpin' : 'Pin'}</Btn>}
                  {m.player_id && !m.from_staff && <Btn size="sm" icon={BsVolumeMute} onClick={() => setMuting(m)}>Mute</Btn>}
                  <Btn size="sm" variant="danger" icon={BsTrash} onClick={() => moderate([m.id], 'delete')} aria-label="Delete for good" />
                </div>
              </div>
            ))}
          </div>

          <form onSubmit={post} className="flex gap-2 border-t border-border/60 p-3">
            <TextInput value={text} onChange={(e) => setText(e.target.value)} maxLength={500} placeholder={`Post in ${room?.name ?? 'this room'} as ${user?.username ?? 'staff'} (shown with a Team badge)`} aria-label="Message" />
            <Btn type="submit" variant="primary" busy={busy} disabled={!text.trim()}>Post</Btn>
          </form>
        </Panel>
      </div>

      <Panel title="Muted players" description="They can read every room they belong to but can’t post." padded={false}>
        {(data?.mutes.length ?? 0) === 0 ? <p className="px-4 py-5 text-sm text-muted-foreground">Nobody is muted.</p> : (
          <ul className="divide-y divide-border/60">
            {data!.mutes.map((m) => (
              <li key={m.player_id} className="flex flex-wrap items-center gap-3 px-4 py-3 text-sm">
                <Link href={`/players/${m.player_id}`} className="font-semibold hover:underline">{m.username}</Link>
                <span className="text-xs text-muted-foreground">{m.until ? `until ${new Date(m.until).toLocaleString([], { dateStyle: 'medium', timeStyle: 'short' })}` : 'until lifted'} · by {m.muted_by}{m.reason ? ` · ${m.reason}` : ''}</span>
                <span className="flex-1" />
                <Btn size="sm" onClick={() => unmute(m)}>Unmute</Btn>
              </li>
            ))}
          </ul>
        )}
      </Panel>

      <RoomDrawer room={editing} audiences={data?.audiences ?? []} canDelete={!!user?.isSuperuser}
        onClose={() => setEditing(null)}
        onSaved={(text, removedId) => { setEditing(null); setNotice({ tone: 'green', text }); if (removedId === roomId) setRoomId(null); refetch(); }} />
      <MuteDrawer message={muting} onClose={() => setMuting(null)}
        onDone={(text) => { setMuting(null); setNotice({ tone: 'green', text }); refetch(); }} />
    </div>
  );
}

function RoomDrawer({ room, audiences, canDelete, onClose, onSaved }: {
  room: Room | 'new' | null; audiences: { id: string; label: string }[]; canDelete: boolean;
  onClose: () => void; onSaved: (text: string, removedId?: number) => void;
}) {
  const { accessToken } = useAuth();
  const blank = { name: '', description: '', audience: 'everyone', staff_only_posting: false, is_open: true, slow_mode_seconds: '3', sort_order: '10' };
  const [form, setForm] = useState(blank);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => {
    setError('');
    setForm(room && room !== 'new' ? {
      name: room.name, description: room.description, audience: room.audience, staff_only_posting: room.staff_only_posting,
      is_open: room.is_open, slow_mode_seconds: String(room.slow_mode_seconds), sort_order: String(room.sort_order),
    } : blank);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [room]);
  const existing = room && room !== 'new' ? room : null;

  async function save() {
    if (!accessToken) return;
    setBusy(true); setError('');
    const res = existing
      ? await authedRequest('PATCH', `/admin/chat/rooms/${existing.id}/`, accessToken, form)
      : await authedPost('/admin/chat/rooms/', form, accessToken);
    setBusy(false);
    if (res.error) setError(res.error); else onSaved(existing ? 'Room saved.' : 'Room created.');
  }
  async function remove() {
    if (!accessToken || !existing || !window.confirm(`Delete “${existing.name}” and all ${existing.total} of its messages for good?`)) return;
    setBusy(true);
    const res = await authedRequest('DELETE', `/admin/chat/rooms/${existing.id}/`, accessToken);
    setBusy(false);
    if (res.error) setError(res.error); else onSaved('Room deleted.', existing.id);
  }

  return (
    <Drawer open={room !== null} onClose={onClose} title={existing ? `Room: ${existing.name}` : 'New room'}
      footer={(
        <div className="flex w-full items-center gap-2">
          {existing && canDelete && <Btn variant="danger" busy={busy} onClick={remove}>Delete room</Btn>}
          <span className="flex-1" />
          <Btn onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" busy={busy} disabled={form.name.trim().length < 2} onClick={save}>Save</Btn>
        </div>
      )}>
      <div className="space-y-4">
        {error && <Notice tone="red" onClose={() => setError('')}>{error}</Notice>}
        <Field label="Name"><TextInput value={form.name} maxLength={60} onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
        <Field label="Description" hint="Shown under the room name."><TextInput value={form.description} maxLength={200} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
        <Field label="Who can read it" hint="The team can read and post in every room.">
          <Select value={form.audience} onChange={(e) => setForm({ ...form, audience: e.target.value })}>
            {audiences.map((a) => <option key={a.id} value={a.id}>{a.label}</option>)}
          </Select>
        </Field>
        <Field label="Slow mode (seconds)" hint="How long a member waits between their own messages. 0 = off.">
          <TextInput inputMode="numeric" value={form.slow_mode_seconds} onChange={(e) => setForm({ ...form, slow_mode_seconds: e.target.value.replace(/\D/g, '') })} />
        </Field>
        <Field label="Position" hint="Lower numbers come first in the list.">
          <TextInput inputMode="numeric" value={form.sort_order} onChange={(e) => setForm({ ...form, sort_order: e.target.value.replace(/\D/g, '') })} />
        </Field>
        <label className="flex items-center justify-between gap-4 text-sm">
          <span><b>Only the team posts</b><span className="block text-xs text-muted-foreground">An announcements room: members read, they don’t write.</span></span>
          <Switch checked={form.staff_only_posting} onChange={(v) => setForm({ ...form, staff_only_posting: v })} label="Only the team posts" />
        </label>
        <label className="flex items-center justify-between gap-4 text-sm">
          <span><b>Open</b><span className="block text-xs text-muted-foreground">Off: the room disappears for players; its messages are kept.</span></span>
          <Switch checked={form.is_open} onChange={(v) => setForm({ ...form, is_open: v })} label="Open" />
        </label>
      </div>
    </Drawer>
  );
}

function MuteDrawer({ message, onClose, onDone }: { message: Message | null; onClose: () => void; onDone: (text: string) => void }) {
  const { accessToken } = useAuth();
  const [minutes, setMinutes] = useState('1440');
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  useEffect(() => { setReason(''); setError(''); setMinutes('1440'); }, [message]);

  async function mute() {
    if (!accessToken || !message?.player_id) return;
    setBusy(true); setError('');
    const res = await authedPost('/admin/chat/mutes/', { player_id: message.player_id, minutes: minutes ? Number(minutes) : null, reason }, accessToken);
    setBusy(false);
    if (res.error) setError(res.error); else onDone(`${message.sender} is muted.`);
  }
  return (
    <Drawer open={message !== null} onClose={onClose} title={`Mute ${message?.sender ?? ''}`}
      description="They can still read chat, but can’t post in any room."
      footer={<div className="flex w-full justify-end gap-2"><Btn onClick={onClose}>Cancel</Btn><Btn variant="danger" busy={busy} onClick={mute}>Mute</Btn></div>}>
      <div className="space-y-4">
        {error && <Notice tone="red" onClose={() => setError('')}>{error}</Notice>}
        <Field label="For how long">
          <Select value={minutes} onChange={(e) => setMinutes(e.target.value)}>
            {MUTE_OPTIONS.map(([v, label]) => <option key={label} value={v}>{label}</option>)}
          </Select>
        </Field>
        <Field label="Reason" hint="For the team; the player isn’t shown it."><TextInput value={reason} maxLength={200} onChange={(e) => setReason(e.target.value)} placeholder="Spam / abuse / sharing numbers" /></Field>
      </div>
    </Drawer>
  );
}
