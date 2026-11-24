'use client';

import { useState } from 'react';
import { BsStars } from 'react-icons/bs';
import { Badge, Btn, Field, Notice, PageHeader, Panel, Select, TextInput } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';

interface Grant {
  id: number; audience: string; audience_label: string; amount: string; count: number; message: string; players: number;
  expires_at: string; created_by: string; created_at: string; spins: number; claimed: number; used: number; cost_if_all_used: string;
}

const money = (v: string | number) => `$${Number(v).toFixed(2)}`;

/** Aviator free spins: give players free bets they claim on the Aviator page. */
export default function FreeSpinsPage() {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<{ results: Grant[]; can_grant: boolean }>('/admin/jet/free-spins/');
  const [form, setForm] = useState({ audience: 'all', usernames: '', amount: '1', count: '5', days: '7', message: '' });
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((f) => ({ ...f, [k]: e.target.value }));

  async function give() {
    if (!accessToken) return;
    const total = Number(form.amount) * Number(form.count);
    if (!window.confirm(`Give ${form.count} free spin(s) of ${money(form.amount)} (up to ${money(total)} each) to ${
      form.audience === 'usernames' ? 'the listed players' : form.audience === 'depositors' ? 'every player who has deposited' : 'every player'}?`)) return;
    setBusy(true); setNotice(null);
    const res = await authedPost<Grant & { not_found: string[] }>('/admin/jet/free-spins/', form, accessToken);
    setBusy(false);
    if (res.error || !res.data) { setNotice({ tone: 'red', text: res.error ?? 'Could not give the spins.' }); return; }
    const missing = res.data.not_found?.length ? ` Not found: ${res.data.not_found.join(', ')}.` : '';
    setNotice({ tone: 'green', text: `Given to ${res.data.players} player${res.data.players === 1 ? '' : 's'} (${res.data.spins} spins). They’ve been notified.${missing}` });
    refetch();
  }

  return (
    <div className="space-y-6">
      <PageHeader icon={BsStars} eyebrow="Promotions & bonuses" title="Aviator free spins"
        description="Give players free Aviator bets. They’re notified, claim them on the Aviator page and play them like any bet: the stake costs nothing, a win pays the winnings as bonus." />
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}

      <Panel title="Give free spins" description={data && !data.can_grant ? 'Only a superuser can give free spins.' : undefined}>
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-4">
            <Field label="Who">
              <Select value={form.audience} onChange={set('audience')}>
                <option value="all">All players</option>
                <option value="depositors">Players who have deposited</option>
                <option value="usernames">Chosen players</option>
              </Select>
            </Field>
            <Field label="Value of each spin ($)"><TextInput inputMode="decimal" value={form.amount} onChange={set('amount')} /></Field>
            <Field label="Spins per player"><TextInput inputMode="numeric" value={form.count} onChange={set('count')} /></Field>
            <Field label="Days to claim and use"><TextInput inputMode="numeric" value={form.days} onChange={set('days')} /></Field>
          </div>
          {form.audience === 'usernames' && (
            <Field label="Usernames" hint="Separated by commas, spaces or new lines.">
              <textarea value={form.usernames} onChange={set('usernames')} rows={3}
                className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm" />
            </Field>
          )}
          <Field label="Message (optional)" hint="Shown on the claim banner and in the notification.">
            <TextInput value={form.message} onChange={set('message')} maxLength={200} placeholder="Weekend spins on us" />
          </Field>
          <Btn variant="primary" busy={busy} disabled={!data?.can_grant} onClick={give}>Give spins</Btn>
        </div>
      </Panel>

      <Panel title="Given">
        {!data?.results.length ? <p className="text-sm text-muted-foreground">No free spins given yet.</p> : (
          <ul className="divide-y divide-border/70">
            {data.results.map((g) => (
              <li key={g.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
                <div className="min-w-0">
                  <p className="font-semibold">{g.count} × {money(g.amount)} <Badge tone="slate">{g.audience_label}</Badge>
                    {new Date(g.expires_at) < new Date() && <Badge tone="gold">Ended</Badge>}</p>
                  <p className="text-xs text-muted-foreground">{g.players} players · by {g.created_by} · {new Date(g.created_at).toLocaleString()}
                    {g.message ? ` · “${g.message}”` : ''}</p>
                </div>
                <p className="text-xs tabular-nums">
                  <b>{g.claimed}</b>/{g.spins} claimed · <b>{g.used}</b> played · up to {money(g.cost_if_all_used)}
                </p>
              </li>
            ))}
          </ul>
        )}
      </Panel>
    </div>
  );
}
