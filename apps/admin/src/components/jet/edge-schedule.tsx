'use client';

import { useEffect, useState } from 'react';
import { BsArrowRepeat, BsClock, BsPlusLg, BsTrash3 } from 'react-icons/bs';
import { Badge, Btn, Field, Notice, Panel, Switch, TextInput, cx, tableClass, tdClass, thClass, trClass } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';

interface Rule {
  id: number; name: string; days: string; days_label: string; starts: string; ends: string; overnight: boolean;
  house_edge_percent: string; rtp_percent: string; enabled: boolean; sort_order: number; updated_by: string;
}
interface Schedule {
  enabled: boolean; time_zone: string; standard_edge_percent: string;
  rotation: { enabled: boolean; minutes: number; steps: Step[]; active: number; average_edge_percent: string | null; average_rtp_percent: string | null };
  now: { house_edge_percent: string; rtp_percent: string; rule: string };
  next_change: { at: string; house_edge_percent: string; rule: string } | null;
  rules: Rule[];
}

interface Step { edge: string; on: boolean }

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
  const [rot, setRot] = useState<{ minutes: string; steps: Step[]; add: string } | null>(null);
  useEffect(() => {
    if (data) setRot({ minutes: String(data.rotation.minutes), steps: data.rotation.steps.map((st) => ({ edge: String(Number(st.edge)), on: st.on })), add: '' });
  }, [data]);
  const onEdges = rot ? rot.steps.filter((st) => st.on).map((st) => Number(st.edge)) : [];
  const draftAvg = onEdges.length ? onEdges.reduce((a, b) => a + b, 0) / onEdges.length : null;
  const dirtyRot = !!(rot && data) && (rot.minutes !== String(data.rotation.minutes)
    || JSON.stringify(rot.steps) !== JSON.stringify(data.rotation.steps.map((st) => ({ edge: String(Number(st.edge)), on: st.on }))));

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
          <Switch checked={data.enabled} label="Time windows on"
            onChange={(v) => call('PUT', URL, { enabled: v }, v ? 'Time windows on.' : 'Time windows off.', 'toggle')} />
          Time windows on
        </span>
      )}>
      {notice && <div className="mb-4"><Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice></div>}
      {data && (
        <div className="space-y-5">
          {rot && (
            <div className={cx('space-y-3 rounded-xl border p-4', data.rotation.enabled ? 'border-secondary/50 bg-secondary/5' : 'border-border')}>
              <div className="flex flex-wrap items-center justify-between gap-3">
                <p className="flex items-center gap-2 text-sm font-bold"><BsArrowRepeat size={14} /> Automatic rotation</p>
                <span className="flex items-center gap-2 text-sm font-semibold">
                  <Switch checked={data.rotation.enabled} label="Rotation on"
                    onChange={(v) => call('PUT', URL, { rotation: { enabled: v } }, v ? 'Rotation on: the edge now changes on its own.' : 'Rotation off.', 'rot')} />
                  Rotation on
                </span>
              </div>
              <p className="text-xs text-muted-foreground">
                The edge steps through the list, one value every N minutes, round the clock, then starts again. While on, it
                takes priority over the time windows below.
              </p>
              <div className="space-y-2">
                <p className="text-xs font-semibold">House edges, in order. Tap one to switch it on or off; only the ones on are used.</p>
                <div className="flex flex-wrap gap-2">
                  {rot.steps.map((st, i) => (
                    <span key={i} className={cx('inline-flex items-center overflow-hidden rounded-full border text-sm font-bold',
                      st.on ? 'border-secondary bg-secondary/15' : 'border-border text-muted-foreground line-through opacity-60')}>
                      <button type="button" aria-pressed={st.on} aria-label={`${st.edge}% ${st.on ? 'on' : 'off'}`}
                        onClick={() => setRot({ ...rot, steps: rot.steps.map((x, j) => (j === i ? { ...x, on: !x.on } : x)) })}
                        className="flex items-center gap-1.5 py-1 pl-3 pr-2">
                        <span className={cx('h-2 w-2 rounded-full', st.on ? 'bg-win' : 'bg-muted-foreground/50')} />{st.edge}%
                      </button>
                      <button type="button" aria-label={`Remove ${st.edge}%`} onClick={() => setRot({ ...rot, steps: rot.steps.filter((_, j) => j !== i) })}
                        className="border-l border-border/60 px-2 py-1 text-xs text-muted-foreground hover:text-live">×</button>
                    </span>
                  ))}
                  <span className="inline-flex items-center gap-1">
                    <input value={rot.add} inputMode="decimal" placeholder="add %" aria-label="Add a house edge"
                      onChange={(e) => setRot({ ...rot, add: e.target.value.replace(/[^0-9.]/g, '') })}
                      onKeyDown={(e) => { if (e.key === 'Enter' && rot.add) setRot({ ...rot, steps: [...rot.steps, { edge: String(Number(rot.add)), on: true }], add: '' }); }}
                      className="h-8 w-20 rounded-full border border-border bg-input/60 px-3 text-center text-xs outline-none focus:border-secondary" />
                    <Btn size="sm" disabled={!rot.add} onClick={() => setRot({ ...rot, steps: [...rot.steps, { edge: String(Number(rot.add)), on: true }], add: '' })}>Add</Btn>
                  </span>
                </div>
                <div className="flex flex-wrap gap-2 text-xs">
                  <button type="button" className="font-semibold text-secondary" onClick={() => setRot({ ...rot, steps: rot.steps.map((x) => ({ ...x, on: true })) })}>All on</button>
                  <span className="text-muted-foreground">·</span>
                  <button type="button" className="font-semibold text-secondary" onClick={() => setRot({ ...rot, steps: rot.steps.map((x) => ({ ...x, on: false })) })}>All off</button>
                </div>
              </div>
              <div className="flex flex-wrap items-end gap-3">
                <Field label="Change every (minutes)" className="w-44">
                  <TextInput inputMode="numeric" value={rot.minutes} onChange={(e) => setRot({ ...rot, minutes: e.target.value.replace(/\D/g, '') })} />
                </Field>
                <Btn variant="primary" busy={busy === 'rotsave'} disabled={!dirtyRot || rot.steps.length === 0}
                  onClick={() => call('PUT', URL, { rotation: { minutes: Number(rot.minutes), steps: rot.steps } }, 'Rotation saved.', 'rotsave')}>
                  Save rotation
                </Btn>
                {dirtyRot && <span className="text-xs text-gold">Unsaved changes</span>}
              </div>
              <p className={cx('text-xs', draftAvg != null && draftAvg > 10 ? 'rounded-lg border border-gold/40 bg-gold/10 p-2 text-gold' : 'text-muted-foreground')}>
                {draftAvg == null
                  ? 'Every edge is off: while the rotation is on, the time windows (or the standard edge) apply.'
                  : `${onEdges.length} of ${rot.steps.length} on · average edge ${draftAvg.toFixed(2)}% · players get back about ${(100 - draftAvg).toFixed(2)}% over time.`}
                {draftAvg != null && draftAvg > 10 && ` At a ${Math.max(...onEdges)}% edge about ${Math.round(Math.max(...onEdges))}% of rounds crash at 1.00x before the plane moves. Each round shows its edge, so players can see the cycle and wait for the low slots. Most crash games run 1–5%.`}
              </p>
            </div>
          )}
          <div className="grid gap-3 sm:grid-cols-3">
            <div className="rounded-xl border border-border bg-card p-4">
              <p className="text-xs text-muted-foreground">In force now</p>
              <p className="mt-1 text-xl font-bold tabular-nums">{Number(data.now.house_edge_percent).toFixed(2)}%</p>
              <p className="text-xs text-muted-foreground">RTP {Number(data.now.rtp_percent).toFixed(2)}% · {data.now.rule || 'standard edge'}</p>
            </div>
            <div className="rounded-xl border border-border bg-card p-4">
              <p className="text-xs text-muted-foreground">Next change</p>
              <p className="mt-1 text-xl font-bold tabular-nums">{data.next_change ? `${Number(data.next_change.house_edge_percent).toFixed(2)}%` : '—'}</p>
              <p className="text-xs text-muted-foreground">{data.next_change ? `${at(data.next_change.at)} · ${data.next_change.rule || 'standard edge'}` : data.enabled || data.rotation.enabled ? 'No change in the next 7 days' : 'Rotation and windows off'}</p>
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
