'use client';

import { useEffect, useMemo, useRef, useState } from 'react';
import { cn } from '../lib/utils';

/* Shared pieces for the analytics screens (affiliate dashboard and admin):
   the timeframe picker, the "live" indicator and a single-series bar chart. */

export const TIMEFRAMES: { key: string; label: string }[] = [
  { key: 'live', label: 'Live (1h)' },
  { key: 'today', label: 'Today' },
  { key: 'yesterday', label: 'Yesterday' },
  { key: '7d', label: '7 days' },
  { key: '30d', label: '30 days' },
  { key: '90d', label: '90 days' },
  { key: 'this_month', label: 'This month' },
  { key: 'last_month', label: 'Last month' },
  { key: 'this_year', label: 'This year' },
  { key: 'all', label: 'All time' },
  { key: 'custom', label: 'Custom' },
];

export interface TimeframeValue { frame: string; start?: string; end?: string }

/** Query string for an analytics endpoint. */
export function timeframeQuery(v: TimeframeValue): string {
  const q = new URLSearchParams({ frame: v.frame });
  if (v.frame === 'custom' && v.start && v.end) { q.set('start', v.start); q.set('end', v.end); }
  return q.toString();
}

const isoDay = (d: Date) => d.toISOString().slice(0, 10);

/** One row of timeframe chips; "Custom" reveals a from/to date pair. */
export function TimeframePicker({ value, onChange, className }: {
  value: TimeframeValue; onChange: (v: TimeframeValue) => void; className?: string;
}) {
  const [start, setStart] = useState(value.start ?? isoDay(new Date(Date.now() - 6 * 864e5)));
  const [end, setEnd] = useState(value.end ?? isoDay(new Date()));
  return (
    <div className={cn('space-y-2', className)}>
      <div className="-mx-1 flex gap-1.5 overflow-x-auto px-1 pb-1" role="tablist" aria-label="Timeframe">
        {TIMEFRAMES.map((t) => (
          <button
            key={t.key} role="tab" aria-selected={value.frame === t.key}
            onClick={() => onChange(t.key === 'custom' ? { frame: 'custom', start, end } : { frame: t.key })}
            className={cn(
              'shrink-0 rounded-full border px-3 py-1.5 text-xs font-bold transition-colors',
              value.frame === t.key
                ? 'border-secondary bg-secondary text-secondary-foreground'
                : 'border-border bg-card text-muted-foreground hover:text-foreground',
            )}
          >
            {t.label}
          </button>
        ))}
      </div>
      {value.frame === 'custom' && (
        <div className="flex flex-wrap items-center gap-2 text-xs">
          <label className="flex items-center gap-1.5 text-muted-foreground">
            From
            <input type="date" value={start} max={end} onChange={(e) => setStart(e.target.value)}
              className="rounded-md border border-border bg-card px-2 py-1 text-foreground" />
          </label>
          <label className="flex items-center gap-1.5 text-muted-foreground">
            To
            <input type="date" value={end} min={start} onChange={(e) => setEnd(e.target.value)}
              className="rounded-md border border-border bg-card px-2 py-1 text-foreground" />
          </label>
          <button onClick={() => onChange({ frame: 'custom', start, end })}
            className="rounded-md bg-secondary px-3 py-1 font-bold text-secondary-foreground">Apply</button>
        </div>
      )}
    </div>
  );
}

/** Pulsing dot + "updated hh:mm:ss"; turns amber while a refresh is late. */
export function LiveIndicator({ updatedAt, refreshing, intervalMs }: {
  updatedAt: number | null; refreshing?: boolean; intervalMs: number;
}) {
  const [, tick] = useState(0);
  useEffect(() => {
    const t = window.setInterval(() => tick((n) => n + 1), 1000);
    return () => window.clearInterval(t);
  }, []);
  const stale = updatedAt != null && Date.now() - updatedAt > intervalMs * 3;
  return (
    <span className="inline-flex items-center gap-2 text-xs font-semibold text-muted-foreground" aria-live="off">
      <span className="relative flex h-2.5 w-2.5">
        {!stale && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-win opacity-60" />}
        <span className={cn('relative inline-flex h-2.5 w-2.5 rounded-full', stale ? 'bg-gold' : 'bg-win')} />
      </span>
      {stale ? 'Reconnecting…' : 'Live'}
      {updatedAt != null && (
        <span className="tabular-nums">· updated {new Date(updatedAt).toLocaleTimeString()}{refreshing ? '…' : ''}</span>
      )}
    </span>
  );
}

/** Polls `load` every `ms` while the tab is visible; returns the last success time. */
export function usePolling(load: () => void, ms: number, deps: unknown[] = []) {
  const ref = useRef(load);
  ref.current = load;
  useEffect(() => {
    const t = window.setInterval(() => {
      if (document.visibilityState === 'visible') ref.current();
    }, ms);
    const onVisible = () => { if (document.visibilityState === 'visible') ref.current(); };
    document.addEventListener('visibilitychange', onVisible);
    return () => { window.clearInterval(t); document.removeEventListener('visibilitychange', onVisible); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ms, ...deps]);
}

export function formatBucket(iso: string, bucket: string, long = false): string {
  const d = new Date(iso);
  if (bucket === 'minute' || bucket === 'hour') {
    const time = d.toLocaleTimeString(undefined, { hour: '2-digit', minute: '2-digit' });
    return long ? `${d.toLocaleDateString(undefined, { day: 'numeric', month: 'short' })}, ${time}` : time;
  }
  if (bucket === 'day') return d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', ...(long ? { year: 'numeric' } : {}) });
  return d.toLocaleDateString(undefined, { month: 'short', year: long ? 'numeric' : '2-digit' });
}

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const mag = 10 ** Math.floor(Math.log10(v));
  const n = v / mag;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * mag;
}

/**
 * One measure over time as bars, from a zero baseline (negative values hang
 * below it). Recessive grid, three y labels, first/middle/last x labels, and
 * a tooltip for the bar under the pointer. A table view is one click away.
 */
export function BarChart({ points, bucket, format, label, height = 200 }: {
  points: { t: string; v: number }[]; bucket: string; format: (v: number) => string; label: string; height?: number;
}) {
  const [hover, setHover] = useState<number | null>(null);
  const [table, setTable] = useState(false);
  const { top, bottom } = useMemo(() => {
    const max = Math.max(0, ...points.map((p) => p.v));
    const min = Math.min(0, ...points.map((p) => p.v));
    return { top: max > 0 ? niceMax(max) : 0, bottom: min < 0 ? -niceMax(-min) : 0 };
  }, [points]);
  const span = top - bottom || 1;
  const zero = (top / span) * 100; // % from the top where the baseline sits
  const ticks = [top, bottom !== 0 ? 0 : top / 2, bottom].filter((v, i, a) => a.indexOf(v) === i);
  const total = points.reduce((s, p) => s + p.v, 0);
  const labelIdx = points.length > 2 ? [0, Math.floor((points.length - 1) / 2), points.length - 1] : points.map((_, i) => i);
  const h = hover != null ? points[hover] : null;

  return (
    <div>
      <div className="mb-2 flex items-center justify-between gap-2 text-xs text-muted-foreground">
        <span>{label} · total <b className="tabular-nums text-foreground">{format(total)}</b></span>
        <button onClick={() => setTable((v) => !v)} className="font-semibold underline-offset-2 hover:underline">
          {table ? 'Show chart' : 'Show table'}
        </button>
      </div>
      {table ? (
        <div className="max-h-[260px] overflow-auto rounded-lg border border-border">
          <table className="w-full text-xs">
            <thead className="sticky top-0 bg-card text-left text-muted-foreground"><tr><th className="px-3 py-1.5">Period</th><th className="px-3 py-1.5 text-right">{label}</th></tr></thead>
            <tbody>
              {points.map((p) => (
                <tr key={p.t} className="border-t border-border"><td className="px-3 py-1.5">{formatBucket(p.t, bucket, true)}</td><td className="px-3 py-1.5 text-right tabular-nums">{format(p.v)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : (
        <div className="flex gap-2">
          <div className="relative w-14 shrink-0 text-right text-[10px] tabular-nums text-muted-foreground" style={{ height }}>
            {ticks.map((v) => (
              <span key={v} className="absolute right-0 -translate-y-1/2" style={{ top: `${((top - v) / span) * 100}%` }}>{format(v)}</span>
            ))}
          </div>
          <div className="relative min-w-0 flex-1">
            <div className="relative" style={{ height }} onMouseLeave={() => setHover(null)}>
              {ticks.map((v) => (
                <div key={v} className={cn('absolute inset-x-0 border-t', v === 0 ? 'border-muted-foreground/40' : 'border-dashed border-border')}
                  style={{ top: `${((top - v) / span) * 100}%` }} />
              ))}
              <div className="absolute inset-0 flex items-stretch gap-[2px]">
                {points.map((p, i) => {
                  const pct = (Math.abs(p.v) / span) * 100;
                  return (
                    <div key={p.t} className="relative flex-1" onMouseEnter={() => setHover(i)} onFocus={() => setHover(i)}
                      tabIndex={0} aria-label={`${formatBucket(p.t, bucket, true)}: ${format(p.v)}`}>
                      {p.v !== 0 && (
                        <div
                          className={cn('absolute inset-x-0 mx-auto max-w-[28px] bg-secondary transition-opacity',
                            p.v > 0 ? 'rounded-t-[4px]' : 'rounded-b-[4px]', hover != null && hover !== i && 'opacity-60')}
                          style={p.v > 0
                            ? { bottom: `${100 - zero}%`, height: `max(${pct}%, 2px)` }
                            : { top: `${zero}%`, height: `max(${pct}%, 2px)` }}
                        />
                      )}
                    </div>
                  );
                })}
              </div>
              {h && hover != null && (
                <div className="pointer-events-none absolute -top-2 z-10 -translate-x-1/2 -translate-y-full whitespace-nowrap rounded-lg border border-border bg-card px-2.5 py-1.5 text-xs shadow-lg"
                  style={{ left: `${((hover + 0.5) / points.length) * 100}%` }}>
                  <p className="text-muted-foreground">{formatBucket(h.t, bucket, true)}</p>
                  <p className="font-bold tabular-nums text-foreground">{format(h.v)}</p>
                </div>
              )}
            </div>
            <div className="relative mt-1 h-4 text-[10px] text-muted-foreground">
              {labelIdx.map((i) => (
                <span key={i} className={cn('absolute whitespace-nowrap', i === 0 ? 'left-0' : i === points.length - 1 ? 'right-0' : '-translate-x-1/2')}
                  style={i !== 0 && i !== points.length - 1 ? { left: `${((i + 0.5) / points.length) * 100}%` } : undefined}>
                  {points[i] && formatBucket(points[i].t, bucket)}
                </span>
              ))}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
