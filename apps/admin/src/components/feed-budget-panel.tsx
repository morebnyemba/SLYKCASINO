'use client';

import { BsSpeedometer2 } from 'react-icons/bs';
import { Badge, Panel, cx, tableClass, tdClass, thClass, trClass } from '@/components/console/ui';

export interface FeedBudget {
  day: string; resets_in_seconds: number; limit: number; used_by_us: number; remaining: number; reserve: number;
  remaining_reported_at: string | null; projected_today: number | null;
  jobs: {
    kind: string; label: string; critical: boolean; base_seconds: number; interval_seconds: number | null;
    last_run_at: string | null; runs_today: number; skipped_today: number; requests_today: number; cost_per_run: number | null;
  }[];
}

function every(s: number | null) {
  if (s === null) return 'paused until reset';
  if (s <= 0) return 'on demand';
  if (s < 90) return `every ${Math.round(s)}s`;
  if (s < 5400) return `every ${Math.round(s / 60)} min`;
  return `every ${(s / 3600).toFixed(s % 3600 ? 1 : 0)} h`;
}

function hm(seconds: number) {
  const h = Math.floor(seconds / 3600);
  const m = Math.round((seconds % 3600) / 60);
  return h ? `${h} h ${m} min` : `${m} min`;
}

/** The feed manager: today's api-football quota and how often each fetch runs right now. */
export function FeedBudgetPanel({ budget }: { budget: FeedBudget | null | undefined }) {
  if (!budget) return null;
  const used = budget.limit - budget.remaining;
  const pct = budget.limit ? Math.min(100, (used / budget.limit) * 100) : 0;
  const tight = budget.remaining <= budget.reserve;
  return (
    <Panel
      title={<span className="flex items-center gap-2"><BsSpeedometer2 size={14} />API budget</span>}
      description={`The feed manager paces every fetch so the day's quota lasts until it resets (00:00 UTC, in ${hm(budget.resets_in_seconds)}). Intervals stretch automatically on a busy day; ${budget.reserve.toLocaleString()} requests are kept for settling bets.`}
      padded={false}
    >
      <div className="space-y-2 px-5 py-4">
        <div className="flex flex-wrap items-baseline justify-between gap-2 text-sm">
          <span><b className="tabular-nums text-lg">{budget.remaining.toLocaleString()}</b> of {budget.limit.toLocaleString()} requests left today</span>
          <span className="text-muted-foreground">
            {budget.used_by_us.toLocaleString()} sent by the sportsbook
            {budget.projected_today !== null && <> · on pace for {budget.projected_today.toLocaleString()} today</>}
          </span>
        </div>
        <div className="h-2 overflow-hidden rounded-full bg-muted">
          <div className={cx('h-full rounded-full', tight ? 'bg-red-500' : pct > 80 ? 'bg-amber-500' : 'bg-secondary')} style={{ width: `${pct}%` }} />
        </div>
        {tight && <p className="text-xs font-semibold text-red-500">Down to the reserve: only settlement and operator checks call the provider until the reset.</p>}
      </div>
      <div className="overflow-x-auto border-t border-border/60">
        <table className={tableClass}>
          <thead><tr>
            <th className={thClass}>Fetch</th><th className={thClass}>Runs now</th><th className={thClass}>Quiet-day pace</th>
            <th className={thClass}>Requests today</th><th className={thClass}>Runs / skipped</th><th className={thClass}>Per run</th>
          </tr></thead>
          <tbody>
            {budget.jobs.filter((j) => j.kind !== 'manual' || j.requests_today > 0).map((j) => (
              <tr key={j.kind} className={trClass}>
                <td className={tdClass}>
                  <span className="font-semibold">{j.label}</span>
                  {j.critical && <Badge tone="slate" className="ml-2">uses reserve</Badge>}
                </td>
                <td className={cx(tdClass, j.interval_seconds !== null && j.interval_seconds > j.base_seconds * 1.05 && 'font-semibold text-amber-500')}>
                  {every(j.interval_seconds)}
                </td>
                <td className={cx(tdClass, 'text-muted-foreground')}>{every(j.base_seconds)}</td>
                <td className={cx(tdClass, 'tabular-nums')}>{j.requests_today.toLocaleString()}</td>
                <td className={cx(tdClass, 'tabular-nums text-muted-foreground')}>{j.runs_today.toLocaleString()} / {j.skipped_today.toLocaleString()}</td>
                <td className={cx(tdClass, 'tabular-nums text-muted-foreground')}>{j.cost_per_run ?? '—'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  );
}
