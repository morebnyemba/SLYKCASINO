'use client';

import { useState } from 'react';
import { BsClock, BsPlusLg, BsTrash3 } from 'react-icons/bs';
import { Badge, Btn, Field, Notice, Panel, Switch, TextInput, cx, tableClass, tdClass, thClass, trClass } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';

interface Rule {
  id: number; name: string; days: string; days_label: string; starts: string; ends: string; overnight: boolean;
  house_edge_percent: string; rtp_percent: string; enabled: boolean; sort_order: number; updated_by: string;
}
interface Schedule {
  enabled: boolean; time_zone: string; standard_edge_percent: string;
  now: { house_edge_percent: string; rtp_percent: string; rule: string };
  next_change: { at: string; house_edge_percent: string; rule: string } | null;
  rules: Rule[];
}

const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun'];
const EMPTY = { name: '', days: '0123456', starts: '18:00', ends: '23:00', house_edge_percent: '4.00' };
const URL = '/admin/jet/edge-schedule/';

/** House edge by time of day and day of week. The clock alone decides it: each round is drawn with the
 *  edge in force when it opens, and the edge is published with the round. */
export function EdgeSchedulePanel() {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<Schedule>(URL);
  const [form, setForm] = useState({ ...EMPTY });
  const [busy, setBusy] = useState('');
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);

  async function call(method: 'PUT' | 'POST' | 'PATCH' | 'DELETE', path: string, body: unknown, ok: string, key: string) {
    if (!accessToken) return false;
    setBusy(key); setNotice(null);
    const res = await authedRequest(method, path, accessToken, body);
    setBusy('');
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: ok });
    refetch();
    return !res.error;
  }

  const toggleDay = (d: number) => setForm((f) => ({
    ...f, days: f.days.includes(String(d)) ? f.days.replace(String(d), '') : [...f.days, String(d)].sort().join(''),
  }));
  // In the schedule's own time zone, so it reads like the rules (not the viewer's browser clock).
  const at = (iso: string) => new Date(iso).toLocaleString(undefined, { weekday: 'short', hour: '2-digit', minute: '2-digit', hour12: false, timeZone: data?.time_zone });

  return (
    <Panel title="House edge schedule"
      description={`A different house edge at chosen times (${data?.time_zone ?? 'players’ time'}). Each round is drawn with the edge in force when it opens, before any bet, and players see it in the round’s fairness details. The first enabled rule that covers the moment wins; outside every rule the standard edge applies.`}
      actions={data && (
        <span className="flex items-center gap-2 text-sm font-semibold">
          <Switch checked={data.enabled} label="Schedule on"
            onChange={(v) => call('PUT', URL, { enabled: v }, v ? 'Schedule on.' : 'Schedule off: the standard edge applies.', 'toggle')} />
          Schedule on
        </span>
      )}>
      {notice && <div className="mb-4"><Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice></div>}
      {data && (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-border bg-card p-4">
              <p className="text-xs text-muted-foreground">In force now</p>
              <p className="mt-1 text-xl font-bold tabular-nums">{Number(data.now.house_edge_percent).toFixed(2)}%</p>
              <p className="text-xs text-muted-foreground">RTP {Number(data.now.rtp_percent).toFixed(2)}% · {data.now.rule || 'standard edge'}</p>
            </div>
            <div className="rounded-xl border border-border bg-card p-4">
              <p className="text-xs text-muted-foreground">Next change</p>
              <p className="mt-1 text-xl font-bold tabular-nums">{data.next_change ? `${Number(data.next_change.house_edge_percent).toFixed(2)}%` : '—'}</p>
              <p className="text-xs text-muted-foreground">{data.next_change ? `${at(data.next_change.at)} · ${data.next_change.rule || 'standard edge'}` : data.enabled ? 'No change in the next 7 days' : 'Schedule off'}</p>
            </div>
            <div className="rounded-xl border border-border bg-card p-4">
              <p className="text-xs text-muted-foreground">Standard edge</p>
              <p className="mt-1 text-xl font-bold tabular-nums">{Number(data.standard_edge_percent).toFixed(2)}%</p>
              <p className="text-xs text-muted-foreground">Outside every rule (set above)</p>
            </div>
          </div>

          {data.rules.length > 0 && (
            <div className="overflow-x-auto rounded-xl border border-border/70">
              <table className={tableClass}>
                <thead><tr>
                  <th className={thClass}>Order</th><th className={thClass}>Name</th><th className={thClass}>Days</th>
                  <th className={thClass}>Time</th><th className={thClass}>Edge</th><th className={cx(thClass, 'text-center')}>On</th><th className={thClass} />
                </tr></thead>
                <tbody>
                  {data.rules.map((r) => (
                    <tr key={r.id} className={cx(trClass, !r.enabled && 'opacity-60')}>
                      <td className={tdClass}>
                        <input type="number" min={0} defaultValue={r.sort_order} aria-label={`Order of ${r.name || 'rule'}`}
                          onBlur={(e) => { const v = Number(e.target.value); if (v !== r.sort_order) void call('PATCH', `${URL}rules/${r.id}/`, { sort_order: v }, 'Order saved.', `o${r.id}`); }}
                          className="h-8 w-16 rounded-lg border border-border bg-input/60 px-2 text-center font-mono text-xs outline-none focus:border-secondary" />
                      </td>
                      <td className={cx(tdClass, 'font-semibold')}>{r.name || '—'}</td>
                      <td className={tdClass}>{r.days_label}</td>
                      <td className={cx(tdClass, 'whitespace-nowrap font-mono text-xs')}>
                        {r.starts}–{r.ends} {r.overnight && r.starts !== r.ends && <Badge tone="slate">past midnight</Badge>}
                        {r.starts === r.ends && <Badge tone="slate">all day</Badge>}
                      </td>
                      <td className={cx(tdClass, 'tabular-nums')}>
                        <input defaultValue={r.house_edge_percent} inputMode="decimal" aria-label={`Edge of ${r.name || 'rule'}`}
                          onBlur={(e) => { const v = e.target.value.replace(/[^0-9.]/g, ''); if (Number(v) !== Number(r.house_edge_percent)) void call('PATCH', `${URL}rules/${r.id}/`, { house_edge_percent: v }, 'Edge saved.', `e${r.id}`); }}
                          className="h-8 w-20 rounded-lg border border-border bg-input/60 px-2 text-center font-mono text-xs outline-none focus:border-secondary" />
                        <span className="ml-1 text-xs text-muted-foreground">% (RTP {Number(r.rtp_percent).toFixed(2)}%)</span>
                      </td>
                      <td className={cx(tdClass, 'text-center')}>
                        <Switch checked={r.enabled} label={`${r.name || 'Rule'} on`}
                          onChange={(v) => call('PATCH', `${URL}rules/${r.id}/`, { enabled: v }, v ? 'Rule on.' : 'Rule off.', `t${r.id}`)} />
                      </td>
                      <td className={cx(tdClass, 'text-right')}>
                        <button onClick={() => confirm(`Delete ${r.name || 'this rule'}?`) && call('DELETE', `${URL}rules/${r.id}/`, null, 'Rule deleted.', `d${r.id}`)}
                          aria-label={`Delete ${r.name || 'rule'}`} className="rounded-lg p-2 text-muted-foreground hover:bg-live/10 hover:text-live"><BsTrash3 size={13} /></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <div className="space-y-3 rounded-xl border border-dashed border-border p-4">
            <p className="flex items-center gap-2 text-sm font-bold"><BsClock size={13} /> Add a time window</p>
            <div className="grid gap-3 sm:grid-cols-4">
              <Field label="Name"><TextInput value={form.name} maxLength={60} placeholder="e.g. Weekday evenings" onChange={(e) => setForm({ ...form, name: e.target.value })} /></Field>
              <Field label="From"><TextInput type="time" value={form.starts} onChange={(e) => setForm({ ...form, starts: e.target.value })} /></Field>
              <Field label="Until" hint="Earlier than From = runs past midnight; same = all day."><TextInput type="time" value={form.ends} onChange={(e) => setForm({ ...form, ends: e.target.value })} /></Field>
              <Field label="House edge (%)"><TextInput inputMode="decimal" value={form.house_edge_percent} onChange={(e) => setForm({ ...form, house_edge_percent: e.target.value.replace(/[^0-9.]/g, '') })} /></Field>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {DAYS.map((d, i) => (
                <button key={d} type="button" onClick={() => toggleDay(i)} aria-pressed={form.days.includes(String(i))}
                  className={cx('rounded-full border px-3 py-1 text-xs font-bold',
                    form.days.includes(String(i)) ? 'border-secondary bg-secondary text-secondary-foreground' : 'border-border text-muted-foreground')}>
                  {d}
                </button>
              ))}
              <span className="ml-auto" />
              {Number(form.house_edge_percent) > 10 && <span className="text-xs text-gold">Above 10% players notice quickly; most crash games use 1–5%.</span>}
              <Btn variant="primary" icon={BsPlusLg} busy={busy === 'add'}
                onClick={async () => { if (await call('POST', `${URL}rules/`, form, 'Time window added.', 'add')) setForm({ ...EMPTY }); }}>
                Add window
              </Btn>
            </div>
          </div>
        </div>
      )}
    </Panel>
  );
}
