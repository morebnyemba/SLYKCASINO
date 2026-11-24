'use client';

import { useEffect, useState } from 'react';
import { BsGift } from 'react-icons/bs';
import { Badge, Btn, Field, Notice, PageHeader, Panel, Select, TextInput } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';

interface Grant {
  id: number; kind: 'credit' | 'debit'; kind_label: string; audience: string; audience_label: string;
  amount: string; wagering_multiplier: string; name: string; message: string;
  status: 'running' | 'done' | 'failed'; stalled: boolean; players: number; processed: number;
  affected: number; skipped: number; total: string; error: string; created_by: string; created_at: string;
  finished_at: string | null; undo_of: number | null; undone_by: number | null; can_undo: boolean;
}
interface ListResult { results: Grant[]; audiences: [string, string][]; max_per_player: string }
interface Preview { players: number; total: string; affected: number }

const money = (v: string | number) => `$${Number(v).toFixed(2)}`;

/** Give every player (or a group) a bonus at once, or take bonus back. Bonus wallet only. */
export default function BulkBonusPage() {
  const { accessToken, user } = useAuth();
  const superuser = !!user?.isSuperuser;
  const { data, refetch } = useApi<ListResult>(superuser ? '/admin/bulk-grants/' : null);
  const [form, setForm] = useState({ kind: 'credit', audience: 'all', amount: '', wagering_multiplier: '1', name: '', message: '' });
  const [preview, setPreview] = useState<Preview | null>(null);
  const [confirmTotal, setConfirmTotal] = useState('');
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);

  // While a grant runs, refresh every few seconds for its progress.
  const running = data?.results.some((g) => g.status === 'running' && !g.stalled);
  useEffect(() => {
    if (!running) return;
    const t = setInterval(refetch, 3000);
    return () => clearInterval(t);
  }, [running, refetch]);

  const set = (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setForm((f) => ({ ...f, [k]: e.target.value }));
    setPreview(null); setConfirmTotal('');
  };

  async function doPreview() {
    if (!accessToken) return;
    setBusy('preview'); setNotice(null);
    const res = await authedPost<Preview>('/admin/bulk-grants/', { ...form, preview: true }, accessToken);
    setBusy('');
    if (res.error) setNotice({ tone: 'red', text: res.error });
    else setPreview(res.data ?? null);
  }

  async function run() {
    if (!accessToken) return;
    setBusy('run'); setNotice(null);
    const res = await authedPost<Grant>('/admin/bulk-grants/', { ...form, confirm_total: confirmTotal }, accessToken);
    setBusy('');
    if (res.error) { setNotice({ tone: 'red', text: res.error }); return; }
    setNotice({ tone: 'green', text: 'Started. Progress shows below.' });
    setPreview(null); setConfirmTotal('');
    setForm((f) => ({ ...f, amount: '', name: '', message: '' }));
    refetch();
  }

  async function act(g: Grant, action: 'undo' | 'resume') {
    if (!accessToken) return;
    if (action === 'undo' && !window.confirm(`Take back what “${g.name}” gave, as far as it is still in players’ Bonus wallets?`)) return;
    setBusy(`${action}-${g.id}`); setNotice(null);
    const res = await authedPost<Grant>(`/admin/bulk-grants/${g.id}/`, { action }, accessToken);
    setBusy('');
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: action === 'undo' ? 'Undo started.' : 'Resumed.' });
    refetch();
  }

  if (!superuser) {
    return (
      <div className="space-y-6">
        <PageHeader icon={BsGift} eyebrow="Promotions & bonuses" title="Bulk bonus" description="Give or take bonus for many players at once." />
        <Notice tone="red">Only a superuser can use bulk bonuses.</Notice>
      </div>
    );
  }

  const give = form.kind === 'credit';
  return (
    <div className="space-y-6">
      <PageHeader icon={BsGift} eyebrow="Promotions & bonuses" title="Bulk bonus"
        description="Give every player (or a group) a bonus at once, or take bonus back. Only the Bonus wallet is ever touched: deposits and winnings never are. Suspended and self-excluded players are always left out." />
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}

      <Panel title="New bulk grant">
        <div className="space-y-5">
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="What">
              <Select value={form.kind} onChange={set('kind')}>
                <option value="credit">Give a bonus</option>
                <option value="debit">Take back bonus</option>
              </Select>
            </Field>
            <Field label="Who">
              <Select value={form.audience} onChange={set('audience')}>
                {(data?.audiences ?? [['all', 'All players']]).map(([v, l]) => <option key={v} value={v}>{l}</option>)}
              </Select>
            </Field>
            <Field label="Amount per player ($)" hint={give ? `Up to ${money(data?.max_per_player ?? 500)}.` : 'Never more than a player has in Bonus.'}>
              <TextInput inputMode="decimal" value={form.amount} onChange={set('amount')} placeholder="5.00" />
            </Field>
          </div>
          <div className="grid gap-4 sm:grid-cols-3">
            <Field label="Name players see" hint="In their notification and bonus history.">
              <TextInput value={form.name} onChange={set('name')} placeholder="Weekend boost" maxLength={80} />
            </Field>
            {give && (
              <Field label="Wagering (× the bonus)" hint="How much they must bet before it can turn into winnings. 0 = none.">
                <TextInput inputMode="decimal" value={form.wagering_multiplier} onChange={set('wagering_multiplier')} />
              </Field>
            )}
            <Field label="Message (optional)" hint="Replaces the default notification text.">
              <TextInput value={form.message} onChange={set('message')} maxLength={300} />
            </Field>
          </div>
          <div className="flex flex-wrap items-end gap-3">
            <Btn busy={busy === 'preview'} disabled={!form.amount} onClick={doPreview}>Preview</Btn>
            {preview && (
              <>
                <p className="text-sm">
                  {give
                    ? <>Gives <b>{money(form.amount)}</b> to <b>{preview.players}</b> players: <b>{money(preview.total)}</b> in total.</>
                    : <>Takes back from <b>{preview.affected}</b> of {preview.players} players: <b>{money(preview.total)}</b> in total.</>}
                </p>
                <Field label={`Type ${money(preview.total)} to confirm`}>
                  <TextInput value={confirmTotal} onChange={(e) => setConfirmTotal(e.target.value)} placeholder={preview.total} />
                </Field>
                <Btn variant="primary" busy={busy === 'run'} disabled={confirmTotal.replace('$', '').trim() !== preview.total || !form.name}
                  onClick={run}>{give ? 'Give bonus' : 'Take back'}</Btn>
              </>
            )}
          </div>
        </div>
      </Panel>

      <Panel title="History" description="Re-running is safe: nobody is paid twice for one grant.">
        {!data?.results.length ? <p className="text-sm text-muted-foreground">No bulk grants yet.</p> : (
          <ul className="divide-y divide-border/70">
            {data.results.map((g) => {
              const pct = g.players ? Math.round((g.processed / g.players) * 100) : 0;
              return (
                <li key={g.id} className="flex flex-wrap items-center justify-between gap-3 py-3 text-sm">
                  <div className="min-w-0 space-y-1">
                    <p className="font-semibold">
                      {g.name} <Badge tone={g.kind === 'credit' ? 'green' : 'gold'}>{g.kind_label}</Badge>{' '}
                      {g.status === 'done' && <Badge tone="slate">Done</Badge>}
                      {g.status === 'failed' && <Badge tone="red">Failed</Badge>}
                      {g.status === 'running' && (g.stalled ? <Badge tone="red">Stalled</Badge> : <Badge tone="indigo" dot>Running {pct}%</Badge>)}
                      {g.undone_by && <Badge tone="slate">Undone</Badge>}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {money(g.amount)} each · {g.audience_label} · by {g.created_by} · {new Date(g.created_at).toLocaleString()}
                    </p>
                    {g.status !== 'running' && (
                      <p className="text-xs">{g.kind === 'credit' ? 'Given to' : 'Taken from'} <b>{g.affected}</b> players · <b>{money(g.total)}</b>
                        {g.skipped ? ` · ${g.skipped} skipped (fraud checks or no bonus)` : ''}</p>
                    )}
                    {g.status === 'running' && (
                      <div className="h-1.5 w-56 overflow-hidden rounded-full bg-muted"><div className="h-full bg-secondary" style={{ width: `${pct}%` }} /></div>
                    )}
                    {g.error && <p className="text-xs text-destructive">{g.error}</p>}
                  </div>
                  <div className="flex gap-2">
                    {(g.stalled || g.status === 'failed') && <Btn size="sm" busy={busy === `resume-${g.id}`} onClick={() => act(g, 'resume')}>Resume</Btn>}
                    {g.can_undo && <Btn size="sm" busy={busy === `undo-${g.id}`} onClick={() => act(g, 'undo')}>Undo</Btn>}
                  </div>
                </li>
              );
            })}
          </ul>
        )}
      </Panel>
    </div>
  );
}
