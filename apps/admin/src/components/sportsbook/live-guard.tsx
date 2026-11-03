'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { Badge, Btn, Field, Notice, Panel, Switch, TextInput } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import type { AdminMatch } from '@/lib/sportsbook';
import { authedPost, authedRequest, useApi } from '@/lib/use-api';

interface LiveSettings {
  lock_minute: number | string; price_jump_percent: number | string; burst_amount: string; burst_minutes: number | string;
  hold_on_bad_feed: boolean;
  held: { id: number; name: string; status: string; elapsed: number | null; reason: string; held_at: string }[];
}

/** In-play guard settings and the matches it is holding right now. */
export function LiveGuardPanel() {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<LiveSettings>('/admin/sportsbook/live-trading/');
  const [form, setForm] = useState<LiveSettings | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  useEffect(() => { if (data) setForm(data); }, [data]);
  useEffect(() => { const t = window.setInterval(refetch, 15000); return () => window.clearInterval(t); }, [refetch]);

  async function save() {
    if (!accessToken || !form) return;
    setBusy(true);
    const { held: _held, ...body } = form;
    const res = await authedRequest('PUT', '/admin/sportsbook/live-trading/', accessToken, body);
    setBusy(false);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: 'Live protection saved.' });
    refetch();
  }

  const set = (k: keyof LiveSettings) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((v) => v && { ...v, [k]: e.target.value.replace(/[^0-9.]/g, '') });

  return (
    <Panel title="Live market protection"
      description="Every live match trades from kick-off until the lock minute (75 by default, by the match clock), when all its markets lock until full time. Otherwise markets stay open unless the feed or your team suspends them: the other automatic holds below are off (0) by default — switch one on only if you need it. You can always suspend a match by hand from its page.">
      {notice && <div className="mb-4"><Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice></div>}
      {(data?.held.length ?? 0) > 0 && (
        <div className="mb-4 space-y-2">
          <p className="text-sm font-semibold text-live">Suspended for review now</p>
          {data!.held.map((h) => (
            <div key={h.id} className="flex flex-wrap items-center gap-2 rounded-xl border border-live/30 p-3 text-sm">
              <Link href={`/sportsbook/matches/${h.id}`} className="font-semibold hover:underline">{h.name}</Link>
              <Badge tone="red" dot>{h.status}{h.elapsed != null ? ` ${h.elapsed}'` : ''}</Badge>
              <span className="text-muted-foreground">{h.reason}</span>
            </div>
          ))}
        </div>
      )}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Field label="Close in-play betting at minute" hint="75 by default. 0 = never.">
          <TextInput inputMode="numeric" value={form?.lock_minute ?? ''} onChange={set('lock_minute')} />
        </Field>
        <Field label="Suspend on a price jump of (%)" hint="Match-result price, in one update, with no goal. 0 = off.">
          <TextInput inputMode="numeric" value={form?.price_jump_percent ?? ''} onChange={set('price_jump_percent')} />
        </Field>
        <Field label="Suspend when in-play stakes on one pick exceed ($)" hint="0 = off.">
          <TextInput inputMode="decimal" value={form?.burst_amount ?? ''} onChange={set('burst_amount')} />
        </Field>
        <Field label="…within (minutes)">
          <TextInput inputMode="numeric" value={form?.burst_minutes ?? ''} onChange={set('burst_minutes')} />
        </Field>
      </div>
      <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
        <Switch checked={!!form?.hold_on_bad_feed} onChange={(v) => setForm((f) => f && { ...f, hold_on_bad_feed: v })}
          label="Suspend when the feed's score goes down or its clock runs backwards" />
        <Btn variant="primary" busy={busy} onClick={save}>Save live protection</Btn>
      </div>
    </Panel>
  );
}

/** On a match page: its in-play state, and suspend / reopen. */
export function LiveControl({ match, onChange }: { match: AdminMatch; onChange: (m: AdminMatch) => void }) {
  const { accessToken } = useAuth();
  const [reason, setReason] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  if (match.state !== 'live' && !match.live_hold_reason && !match.live_locked_at) return null;

  async function act(path: 'live-hold' | 'live-release') {
    if (!accessToken) return;
    setBusy(true); setError('');
    const res = await authedPost<AdminMatch>(`/admin/sportsbook/events/${match.id}/${path}/`,
      path === 'live-hold' ? { reason } : {}, accessToken);
    setBusy(false);
    if (res.error || !res.data) { setError(res.error ?? 'Something went wrong.'); return; }
    setReason('');
    onChange(res.data);
  }

  return (
    <Panel title="In-play betting" description={match.trading.in_play ? 'Trading live now.' : match.trading.live_closed ?? 'Not trading live right now.'}>
      {error && <div className="mb-3"><Notice tone="red" onClose={() => setError('')}>{error}</Notice></div>}
      <div className="flex flex-wrap gap-2">
        {match.live_locked_at && <Badge tone="slate">Closed at the lock minute — stays closed until full time</Badge>}
        {match.live_hold_reason && <Badge tone="red" dot>Suspended: {match.live_hold_reason}</Badge>}
        {match.trading.in_play && <Badge tone="green" dot>Live</Badge>}
      </div>
      {match.live_hold_reason ? (
        <div className="mt-4"><Btn variant="success" busy={busy} onClick={() => act('live-release')}>Reopen in-play betting</Btn>
          {match.live_locked_at && <p className="mt-2 text-xs text-muted-foreground">Reopening clears the suspension, but the match is past the lock minute so it stays closed.</p>}
        </div>
      ) : !match.live_locked_at && (
        <div className="mt-4 flex flex-wrap items-end gap-2">
          <Field label="Suspend in-play betting" hint="Bets in their acceptance delay are refused and refunded." className="min-w-[260px] flex-1">
            <TextInput value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Red card not in the feed yet" />
          </Field>
          <Btn variant="danger" busy={busy} disabled={reason.trim().length < 3} onClick={() => act('live-hold')}>Suspend</Btn>
        </div>
      )}
    </Panel>
  );
}
