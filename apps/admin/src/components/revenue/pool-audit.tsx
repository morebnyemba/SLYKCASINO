'use client';

import { Fragment, useRef, useState } from 'react';
import { BsDownload, BsFileEarmarkSpreadsheet, BsShieldCheck } from 'react-icons/bs';
import {
  Badge, Btn, EmptyState, Field, Notice, Panel, TextInput, cx, money, tableClass, tdClass, thClass, trClass,
} from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { config } from '@/lib/config';
import { authedPost, useApi } from '@/lib/use-api';

type Tone = { tone: 'green' | 'red'; text: string } | null;

// -- pool ledger -------------------------------------------------------------------

interface LedgerRow { day: string; kind: 'day' | 'affiliates' | 'expense'; label: string; amount: string; balance: string }
interface Ledger {
  summary: { earned: string; affiliate_costs: string; expenses: string; remaining: string };
  opening: string; in: string; out: string; closing: string; rows: LedgerRow[];
}
interface Commission { agent: string; kind: string; period: string; ticket: string; base: string; rate: string; amount: string }

function csvCell(v: string) {
  return /[",\n]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v;
}

function AffiliateBreakdown({ day }: { day: string }) {
  const { data } = useApi<{ commissions: Commission[] }>(`/admin/revenue-share/pool/days/${day}/`);
  if (!data) return <p className="px-4 py-2 text-xs text-muted-foreground">Loading…</p>;
  if (!data.commissions.length) return <p className="px-4 py-2 text-xs text-muted-foreground">No commissions found for this day.</p>;
  return (
    <table className="w-full text-xs">
      <tbody>
        {data.commissions.map((c, i) => (
          <tr key={i} className="border-t border-border/40">
            <td className="px-4 py-1.5 font-mono">{c.agent}</td>
            <td className="px-4 py-1.5">{c.kind}{c.ticket ? ` ${c.ticket}` : ''}{c.period ? ` · ${c.period}` : ''}</td>
            <td className="px-4 py-1.5 text-muted-foreground">{money(c.base)} × {Number(c.rate)}%</td>
            <td className="px-4 py-1.5 text-right tabular-nums">{money(c.amount)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Every movement of the operating pool, with a running balance anyone with pool access can check. */
export function PoolLedger() {
  const [from, setFrom] = useState('');
  const [to, setTo] = useState('');
  const [open, setOpen] = useState<string | null>(null);
  const qs = new URLSearchParams({ ...(from && { from }), ...(to && { to }) }).toString();
  const { data } = useApi<Ledger>(`/admin/revenue-share/pool/${qs ? `?${qs}` : ''}`);

  function download() {
    if (!data) return;
    const lines = [['Date', 'Movement', 'Amount', 'Pool balance'].join(','),
      ...data.rows.map((r) => [r.day, csvCell(r.label), r.amount, r.balance].join(','))];
    const url = URL.createObjectURL(new Blob([lines.join('\n')], { type: 'text/csv' }));
    const a = document.createElement('a');
    a.href = url; a.download = `pool-ledger${from ? `-${from}` : ''}${to ? `-to-${to}` : ''}.csv`; a.click();
    URL.revokeObjectURL(url);
  }

  const rows = data ? [...data.rows].reverse() : [];
  return (
    <Panel title="Pool ledger" description="Every movement of the operating pool, oldest to newest, with the balance after each one: each closed day’s share in, that day’s affiliate commissions out (click to see each agent), and every recorded cost out."
      padded={false}
      actions={<Btn size="sm" icon={BsDownload} onClick={download} disabled={!data?.rows.length}>CSV</Btn>}>
      <div className="flex flex-wrap items-end gap-3 px-5 pb-4">
        <Field label="From" className="w-40"><TextInput type="date" value={from} onChange={(e) => setFrom(e.target.value)} /></Field>
        <Field label="To" className="w-40"><TextInput type="date" value={to} onChange={(e) => setTo(e.target.value)} /></Field>
        {data && (
          <div className="ml-auto flex flex-wrap gap-4 text-sm">
            {from && <span>Opening <b className="tabular-nums">{money(data.opening)}</b></span>}
            <span>In <b className="tabular-nums text-win">{money(data.in)}</b></span>
            <span>Out <b className="tabular-nums text-live">{money(data.out)}</b></span>
            <span>In the pool <b className="tabular-nums">{money(data.closing)}</b></span>
          </div>
        )}
      </div>
      {!data ? <div className="h-24 animate-pulse bg-muted/30" /> : rows.length === 0 ? (
        <EmptyState icon={BsFileEarmarkSpreadsheet} title="No pool movements in this range" />
      ) : (
        <div className="max-h-[28rem] overflow-auto">
          <table className={tableClass}>
            <thead className="sticky top-0 bg-card">
              <tr><th className={thClass}>Date</th><th className={thClass}>Movement</th><th className={cx(thClass, 'text-right')}>Amount</th><th className={cx(thClass, 'text-right')}>Pool balance</th></tr>
            </thead>
            <tbody>
              {rows.map((r, i) => {
                const key = `${r.day}-${r.kind}-${i}`;
                return (
                  <Fragment key={key}>
                    <tr className={cx(trClass, r.kind === 'affiliates' && 'cursor-pointer')} onClick={() => r.kind === 'affiliates' && setOpen(open === key ? null : key)}>
                      <td className={cx(tdClass, 'whitespace-nowrap text-xs')}>{r.day}</td>
                      <td className={tdClass}>{r.label}{r.kind === 'affiliates' && <span className="ml-2 text-xs text-secondary">{open === key ? 'hide' : 'details'}</span>}</td>
                      <td className={cx(tdClass, 'text-right font-semibold tabular-nums', Number(r.amount) < 0 ? 'text-live' : 'text-win')}>{money(r.amount)}</td>
                      <td className={cx(tdClass, 'text-right tabular-nums')}>{money(r.balance)}</td>
                    </tr>
                    {open === key && <tr><td colSpan={4} className="bg-muted/30 p-0"><AffiliateBreakdown day={r.day} /></td></tr>}
                  </Fragment>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Panel>
  );
}

// -- weekly audits ------------------------------------------------------------------

type Issue = 'matched' | 'amount_mismatch' | 'other_week' | 'not_credited' | 'unknown' | 'missing_from_report';
interface Problem {
  line: number | null; reference: string; account?: string; amount: string | null; system_amount?: string;
  player_id?: number; request_id?: number; when: string; issue: Issue; detail: string;
}
interface MatchResult {
  manual: boolean; report_total: string; system_total: string; difference: string; balanced: boolean; rows: number;
  counts: Partial<Record<Issue, number>>; problems: Problem[]; file_name?: string; skipped?: number;
}
interface System {
  deposits: { count: number; total: string }; payouts: { count: number; requested: string; fees: string; sent: string };
  ggr: string; days_closed: number; pool_in: string; affiliate_costs: string; expenses: string;
  partner_shares: string; partner_withdrawals: string; pool_balance_end: string;
}
interface Audit {
  week_start: string; week_end: string; status: 'open' | 'review' | 'signed'; status_label: string; system: System;
  paynow: MatchResult | null; payouts: MatchResult | null; paynow_file: boolean; payouts_file: boolean;
  note: string; uploaded_by: string; signed_by: string; signed_at: string | null;
}

const ISSUE: Record<Issue, { label: string; tone: 'green' | 'red' | 'gold' | 'slate' }> = {
  matched: { label: 'Matched', tone: 'green' },
  missing_from_report: { label: 'On the platform, not in the report', tone: 'red' },
  not_credited: { label: 'Paid but never credited', tone: 'red' },
  unknown: { label: 'In the report, not on the platform', tone: 'red' },
  amount_mismatch: { label: 'Amount differs', tone: 'gold' },
  other_week: { label: 'Neighbouring week (timing)', tone: 'slate' },
};
const STATUS_TONE = { open: 'gold', review: 'indigo', signed: 'green' } as const;

function ReportSlot({ week, kind, title, help, result, hasFile, canEdit, onChanged }: {
  week: string; kind: 'paynow' | 'payouts'; title: string; help: string; result: MatchResult | null; hasFile: boolean;
  canEdit: boolean; onChanged: (n: Tone) => void;
}) {
  const { accessToken } = useAuth();
  const input = useRef<HTMLInputElement>(null);
  const [total, setTotal] = useState('');
  const [busy, setBusy] = useState(false);
  const [show, setShow] = useState(false);

  async function send(file?: File) {
    if (!accessToken) return;
    setBusy(true);
    const body = new FormData();
    body.append('kind', kind);
    if (file) body.append('file', file); else body.append('total', total);
    try {
      const res = await fetch(`${config.apiUrl}/admin/revenue-share/audits/${week}/upload/`, {
        method: 'POST', headers: { Authorization: `Bearer ${accessToken}` }, body,
      });
      const json = (await res.json().catch(() => ({}))) as { detail?: string };
      onChanged(res.ok ? { tone: 'green', text: `${title} checked.` } : { tone: 'red', text: json.detail ?? `Upload failed (${res.status}).` });
    } catch {
      onChanged({ tone: 'red', text: 'Upload failed — check your connection.' });
    } finally {
      setBusy(false);
      if (input.current) input.current.value = '';
    }
  }

  async function downloadFile() {
    if (!accessToken) return;
    const res = await fetch(`${config.apiUrl}/admin/revenue-share/audits/${week}/file/${kind}/`, { headers: { Authorization: `Bearer ${accessToken}` } });
    if (!res.ok) return;
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement('a');
    a.href = url; a.download = result?.file_name ?? `${week}-${kind}`; a.click();
    URL.revokeObjectURL(url);
  }

  const problems = result?.problems.filter((p) => p.issue !== 'matched') ?? [];
  return (
    <div className="space-y-3 rounded-xl border border-border/60 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div>
          <p className="font-semibold">{title}</p>
          <p className="text-xs text-muted-foreground">{help}</p>
        </div>
        {result && <Badge tone={result.balanced ? 'green' : 'red'} dot>{result.balanced ? 'Balanced' : 'Doesn’t balance'}</Badge>}
      </div>
      {result ? (
        <>
          <div className="grid grid-cols-3 gap-2 text-sm">
            <div className="rounded-lg bg-muted/50 p-2"><p className="text-[11px] text-muted-foreground">Report</p><p className="font-semibold tabular-nums">{money(result.report_total)}</p></div>
            <div className="rounded-lg bg-muted/50 p-2"><p className="text-[11px] text-muted-foreground">Platform</p><p className="font-semibold tabular-nums">{money(result.system_total)}</p></div>
            <div className="rounded-lg bg-muted/50 p-2"><p className="text-[11px] text-muted-foreground">Difference</p><p className={cx('font-semibold tabular-nums', Number(result.difference) !== 0 && 'text-live')}>{money(result.difference)}</p></div>
          </div>
          {result.manual ? <p className="text-xs text-muted-foreground">Total entered by hand (no line-by-line check).</p> : (
            <div className="flex flex-wrap gap-1.5">
              {(Object.keys(ISSUE) as Issue[]).filter((k) => result.counts[k]).map((k) => (
                <Badge key={k} tone={ISSUE[k].tone}>{result.counts[k]} {ISSUE[k].label.toLowerCase()}</Badge>
              ))}
              {result.skipped ? <Badge tone="slate">{result.skipped} rows skipped (not paid)</Badge> : null}
            </div>
          )}
          {problems.length > 0 && (
            <>
              <button onClick={() => setShow(!show)} className="text-xs font-semibold text-secondary hover:underline">{show ? 'Hide' : 'Show'} the {problems.length} line{problems.length === 1 ? '' : 's'} to check</button>
              {show && (
                <div className="max-h-72 divide-y divide-border/40 overflow-auto rounded-lg border border-border/60 text-xs">
                  {problems.map((p, i) => (
                    <div key={i} className="space-y-1 px-3 py-2">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone={ISSUE[p.issue].tone}>{ISSUE[p.issue].label}</Badge>
                        <span className="font-mono">{p.reference || p.account || '—'}</span>
                        {p.line ? <span className="text-muted-foreground">row {p.line}</span> : null}
                        <span className="ml-auto tabular-nums">
                          {p.amount ? money(p.amount) : '—'}{p.system_amount ? <span className="text-muted-foreground"> · platform {money(p.system_amount)}</span> : null}
                        </span>
                      </div>
                      <p className="text-muted-foreground">{p.detail}{p.player_id ? ` Player #${p.player_id}.` : ''}{p.request_id ? ` Withdrawal #${p.request_id}.` : ''}</p>
                    </div>
                  ))}
                </div>
              )}
            </>
          )}
          {hasFile && <Btn size="sm" variant="ghost" icon={BsDownload} onClick={downloadFile}>{result.file_name ?? 'Download report'}</Btn>}
        </>
      ) : <p className="text-sm text-muted-foreground">Not uploaded yet.</p>}
      {canEdit && (
        <div className="flex flex-wrap items-end gap-2 border-t border-border/50 pt-3">
          <input ref={input} type="file" accept=".csv,.xlsx,.xlsm,.txt" className="hidden" onChange={(e) => e.target.files?.[0] && send(e.target.files[0])} />
          <Btn size="sm" variant="primary" busy={busy} onClick={() => input.current?.click()}>{result ? 'Replace report' : 'Upload CSV / Excel'}</Btn>
          <span className="text-xs text-muted-foreground">or, for a PDF, its total:</span>
          <TextInput inputMode="decimal" value={total} onChange={(e) => setTotal(e.target.value.replace(/[^0-9.]/g, ''))} placeholder="0.00" className="h-8 w-28 text-xs" />
          <Btn size="sm" disabled={!total} busy={busy} onClick={() => send()}>Use total</Btn>
        </div>
      )}
    </div>
  );
}

function SignOff({ a, onChanged }: { a: Audit; onChanged: (n: Tone) => void }) {
  const { accessToken } = useAuth();
  const [note, setNote] = useState(a.note);
  const [busy, setBusy] = useState(false);
  const ready = a.paynow && a.payouts;
  const balanced = a.paynow?.balanced && a.payouts?.balanced;
  async function sign() {
    if (!accessToken || !window.confirm(`Sign off ${a.week_start} – ${a.week_end}? Its figures are frozen and its pool costs locked.`)) return;
    setBusy(true);
    const res = await authedPost(`/admin/revenue-share/audits/${a.week_start}/sign/`, { note }, accessToken);
    setBusy(false);
    onChanged(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: `Week of ${a.week_start} signed off.` });
  }
  return (
    <div className="flex flex-wrap items-end gap-3 border-t border-border/50 pt-4">
      <Field label={balanced ? 'Note (optional)' : 'Explain the differences (required)'} className="min-w-[260px] flex-1">
        <TextInput value={note} onChange={(e) => setNote(e.target.value)} placeholder={balanced ? 'All good' : 'e.g. Paynow fee of $1 deducted at source'} />
      </Field>
      <Btn variant="success" icon={BsShieldCheck} busy={busy} disabled={!ready} onClick={sign}>Sign off the week</Btn>
    </div>
  );
}

/** Each finished week: the founder's Paynow and payouts reports checked line by line, then signed off. */
export function WeeklyAudits() {
  const { data, refetch } = useApi<{ is_founder: boolean; founder: string | null; audits: Audit[] }>('/admin/revenue-share/audits/');
  const [notice, setNotice] = useState<Tone>(null);
  const [openWeek, setOpenWeek] = useState<string | null>(null);
  const changed = (n: Tone) => { setNotice(n); refetch(); };
  const waiting = data?.audits.filter((a) => a.status !== 'signed').length ?? 0;

  return (
    <Panel title="Weekly pool audit"
      description={`Every Monday the week before opens for audit. ${data?.founder ? `${data.founder} (the founder)` : 'The founder'} uploads Paynow’s report of money received and their own report of money paid to players; each line is matched against what the platform recorded. Signing a week off freezes its figures and locks its pool costs.`}
      actions={waiting ? <Badge tone="gold" dot>{waiting} week{waiting === 1 ? '' : 's'} to audit</Badge> : undefined}>
      {notice && <div className="mb-4"><Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice></div>}
      {!data ? <div className="h-24 animate-pulse rounded-xl bg-muted/30" /> : data.audits.length === 0 ? (
        <EmptyState icon={BsShieldCheck} title="No finished weeks yet">The first week opens for audit the Monday after revenue sharing started.</EmptyState>
      ) : (
        <div className="space-y-3">
          {data.audits.map((a) => {
            const isOpen = openWeek === a.week_start || (openWeek === null && a === data.audits.find((x) => x.status !== 'signed'));
            const s = a.system;
            return (
              <div key={a.week_start} className="rounded-xl border border-border/70">
                <button onClick={() => setOpenWeek(isOpen ? '' : a.week_start)} className="flex w-full flex-wrap items-center gap-3 px-4 py-3 text-left">
                  <span className="font-semibold">{a.week_start} – {a.week_end}</span>
                  <Badge tone={STATUS_TONE[a.status]} dot>{a.status_label}</Badge>
                  <span className="ml-auto text-xs text-muted-foreground tabular-nums">
                    Deposits {money(s.deposits.total)} · Payouts {money(s.payouts.sent)} · Pool at week end {money(s.pool_balance_end)}
                  </span>
                </button>
                {isOpen && (
                  <div className="space-y-4 border-t border-border/60 px-4 py-4">
                    <div className="grid gap-2 text-sm sm:grid-cols-3 lg:grid-cols-6">
                      {[['GGR', s.ggr, `${s.days_closed} days closed`], ['Into the pool', s.pool_in, ''], ['Affiliates', `-${s.affiliate_costs}`, ''],
                        ['Costs', `-${s.expenses}`, ''], ['Partners’ shares', s.partner_shares, `${money(s.partner_withdrawals)} withdrawn`],
                        ['Pool at week end', s.pool_balance_end, '']].map(([label, value, hint]) => (
                        <div key={label} className="rounded-lg bg-muted/50 p-2.5">
                          <p className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">{label}</p>
                          <p className="font-semibold tabular-nums">{money(value)}</p>
                          {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
                        </div>
                      ))}
                    </div>
                    <div className="grid gap-3 lg:grid-cols-2">
                      <ReportSlot week={a.week_start} kind="paynow" title="Paynow — money received"
                        help={`Paynow’s transactions export for the week. Platform: ${s.deposits.count} payments, ${money(s.deposits.total)}.`}
                        result={a.paynow} hasFile={a.paynow_file} canEdit={data.is_founder && a.status !== 'signed'} onChanged={changed} />
                      <ReportSlot week={a.week_start} kind="payouts" title="Payouts — money sent to players"
                        help={`Your report of payments to players (phone or reference, amount). Platform: ${s.payouts.count} withdrawals, ${money(s.payouts.sent)} to send after ${money(s.payouts.fees)} fees.`}
                        result={a.payouts} hasFile={a.payouts_file} canEdit={data.is_founder && a.status !== 'signed'} onChanged={changed} />
                    </div>
                    {a.status === 'signed' ? (
                      <p className="text-sm text-muted-foreground">Signed off by <b className="text-foreground">{a.signed_by}</b> on {a.signed_at && new Date(a.signed_at).toLocaleString()}{a.note && <> — “{a.note}”</>}.</p>
                    ) : data.is_founder ? <SignOff a={a} onChanged={changed} /> : (
                      <p className="text-xs text-muted-foreground">Only the founder uploads reports and signs weeks off; you can review everything here.</p>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}
