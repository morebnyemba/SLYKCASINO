'use client';

import Link from 'next/link';
import { BsExclamationTriangleFill, BsLockFill } from 'react-icons/bs';
import { useApi } from '@/lib/use-api';

interface Week { week_start: string; due: string; status: string; waiting_for: string[] }
export interface Governance {
  locked: boolean; lock_weeks: string[]; missed: Week[]; due: Week[]; repeat_offenders: string[]; warning: boolean;
}

/** The deadline is midnight at the end of Tuesday: show it as that Tuesday. */
const when = (iso: string) => `end of ${new Date(Date.parse(iso) - 1).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' })}`;

/** Pool-audit warning for partners: weeks due by Tuesday, weeks missed, and the lock after two in a row.
 *  Shown on the dashboard and the revenue-share page; staff without pool access see nothing. */
export function GovernanceBanner() {
  const { data } = useApi<Governance>('/admin/revenue-share/governance/');
  if (!data || !data.warning) return null;
  const late = data.missed;
  const tone = data.locked ? 'border-live/60 bg-live/10' : late.length ? 'border-live/40 bg-live/5' : 'border-gold/40 bg-gold/5';
  const Icon = data.locked ? BsLockFill : BsExclamationTriangleFill;
  return (
    <div className={`rounded-2xl border px-4 py-3 text-sm ${tone}`} role="alert">
      <div className="flex flex-wrap items-start gap-3">
        <Icon className={data.locked || late.length ? 'mt-0.5 text-live' : 'mt-0.5 text-gold'} />
        <div className="min-w-0 flex-1 space-y-1">
          {data.locked ? (
            <p className="font-bold text-live">
              Money controls are locked: the pool audits for the weeks of {data.lock_weeks.join(' and ')} were both missed.
              The whole admin is read-only — every change is refused — until every missed week is submitted and co-signed.
            </p>
          ) : late.length ? (
            <p className="font-bold text-live">
              {late.length} weekly pool audit{late.length === 1 ? ' is' : 's are'} overdue. Another missed week in a row makes the whole admin read-only.
            </p>
          ) : (
            <p className="font-bold">Weekly pool audit due by the end of Tuesday.</p>
          )}
          {[...late, ...data.due].map((w) => (
            <p key={w.week_start} className="text-muted-foreground">
              Week of {w.week_start} — due by the {when(w.due)} — waiting for <b className="text-foreground">{w.waiting_for.join(', ') || '—'}</b>
            </p>
          ))}
          {data.repeat_offenders.length > 0 && (
            <p className="text-live">Missed two weeks in a row: <b>{data.repeat_offenders.join(', ')}</b>.</p>
          )}
        </div>
        <Link href="/revenue-share" className="rounded-lg border border-border bg-card px-3 py-1.5 text-xs font-semibold hover:bg-muted">Open the audit</Link>
      </div>
    </div>
  );
}
