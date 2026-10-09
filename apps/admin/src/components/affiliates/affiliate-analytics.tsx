'use client';

import { useEffect, useState } from 'react';
import {
  BarChart, LiveIndicator, TimeframePicker, timeframeQuery, usePolling, type TimeframeValue,
} from '@slyk/ui/components/analytics';
import { cx, money } from '@/components/console/ui';
import { useApi } from '@/lib/use-api';

interface Product { plays: number; stakes: string; ggr: string }
interface Data {
  label: string; bucket: string;
  kpis: {
    clicks: number; signups: number; ftds: number; signup_rate: string | null; ftd_rate: string | null; referrals_total: number;
    deposits: string; deposit_count: number; withdrawals: string; depositors: number; active_players: number; plays: number;
    stakes: string; wins: string; player_losses: string; bonuses: string; ngr: string; revshare_estimate: string;
    cpa_earned: string; commission_estimate: string; commission_paid: string; sportsbook: Product; casino: Product;
  };
  series: Record<string, string | number>[];
  campaigns: { campaign: string; clicks: number; signups: number; ftds: number; deposits: string; plays: number; ngr: string }[];
  players: { player: string; deposits: string; plays: number; stakes: string; ngr: string; first_deposit: boolean }[];
}

const count = (v: number) => Math.round(v).toLocaleString();
const signed = (v: number) => (v < 0 ? `−${money(-v)}` : money(v));
const METRICS = [
  ['deposits', 'Deposits', true], ['plays', 'Plays', false], ['ggr', 'Player losses', true], ['ngr', 'NGR', true],
  ['clicks', 'Clicks', false], ['signups', 'Sign-ups', false], ['ftds', 'First deposits', false],
] as const;

/** One affiliate's live analytics, shown inline on the admin affiliates list. */
export function AffiliateAnalyticsPanel({ id }: { id: number }) {
  const [tf, setTf] = useState<TimeframeValue>({ frame: '30d' });
  const [metric, setMetric] = useState<(typeof METRICS)[number]>(METRICS[0]);
  const { data, loading, refetch } = useApi<Data>(`/admin/affiliates/${id}/analytics/?${timeframeQuery(tf)}`);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  usePolling(refetch, 15000, [refetch]);
  useEffect(() => { if (data) setUpdatedAt(Date.now()); }, [data]);
  const k = data?.kpis;

  const tiles: [string, string, string?][] = k ? [
    ['Clicks', count(k.clicks)],
    ['Sign-ups', count(k.signups), k.signup_rate ? `${k.signup_rate}% of clicks` : undefined],
    ['First deposits', count(k.ftds), k.ftd_rate ? `${k.ftd_rate}% of sign-ups` : undefined],
    ['Deposits', money(k.deposits), `${k.deposit_count} by ${k.depositors} players`],
    ['Plays', count(k.plays), `${k.sportsbook.plays} sports · ${k.casino.plays} Aviator`],
    ['Staked', money(k.stakes), `won back ${money(k.wins)}`],
    ['Player losses', signed(Number(k.player_losses)), `${k.active_players} active of ${k.referrals_total} referred`],
    ['NGR', signed(Number(k.ngr)), `after ${money(k.bonuses)} bonuses`],
    ['Commission (est.)', money(k.commission_estimate), `rev share ${money(k.revshare_estimate)} + CPA ${money(k.cpa_earned)}`],
    ['Paid out', money(k.commission_paid), 'in this period'],
  ] : [];

  return (
    <div className="space-y-4 bg-muted/20 p-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-sm font-bold">Analytics{data ? ` · ${data.label}` : ''}</p>
        <LiveIndicator updatedAt={updatedAt} refreshing={loading && !!data} intervalMs={15000} />
      </div>
      <TimeframePicker value={tf} onChange={setTf} />
      {!data ? <div className="h-40 animate-pulse rounded-xl bg-muted/60" /> : (
        <>
          <div className="grid grid-cols-2 gap-2.5 md:grid-cols-5">
            {tiles.map(([label, value, hint]) => (
              <div key={label} className="rounded-xl border border-border/70 bg-card p-3">
                <p className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">{label}</p>
                <p className="mt-0.5 text-lg font-extrabold tabular-nums">{value}</p>
                {hint && <p className="text-[11px] text-muted-foreground">{hint}</p>}
              </div>
            ))}
          </div>
          <div className="rounded-xl border border-border/70 bg-card p-3">
            <div className="mb-3 flex flex-wrap gap-1.5">
              {METRICS.map((m) => (
                <button key={m[0]} onClick={() => setMetric(m)}
                  className={cx('rounded-md px-2.5 py-1 text-xs font-bold', metric[0] === m[0] ? 'bg-secondary text-secondary-foreground' : 'bg-muted/60 text-muted-foreground')}>
                  {m[1]}
                </button>
              ))}
            </div>
            <BarChart label={metric[1]} bucket={data.bucket} height={170}
              points={data.series.map((p) => ({ t: String(p.t), v: Number(p[metric[0]]) }))}
              format={(v) => (metric[2] ? signed(v) : count(v))} />
          </div>
          <div className="grid items-start gap-4 lg:grid-cols-2">
            <table className="w-full text-xs">
              <thead className="text-left text-muted-foreground"><tr><th className="py-1">Campaign</th><th className="text-right">Clicks</th><th className="text-right">Sign-ups</th><th className="text-right">FTDs</th><th className="text-right">Deposits</th><th className="text-right">NGR</th></tr></thead>
              <tbody>
                {data.campaigns.map((c) => (
                  <tr key={c.campaign} className="border-t border-border/60">
                    <td className="py-1.5 font-semibold">{c.campaign}</td><td className="text-right">{c.clicks}</td><td className="text-right">{c.signups}</td>
                    <td className="text-right">{c.ftds}</td><td className="text-right">{money(c.deposits)}</td><td className="text-right font-semibold">{signed(Number(c.ngr))}</td>
                  </tr>
                ))}
                {data.campaigns.length === 0 && <tr><td colSpan={6} className="py-3 text-muted-foreground">No traffic in this period.</td></tr>}
              </tbody>
            </table>
            <table className="w-full text-xs">
              <thead className="text-left text-muted-foreground"><tr><th className="py-1">Player</th><th className="text-right">Deposits</th><th className="text-right">Plays</th><th className="text-right">Staked</th><th className="text-right">NGR</th></tr></thead>
              <tbody>
                {data.players.map((p, i) => (
                  <tr key={i} className="border-t border-border/60">
                    <td className="py-1.5 font-semibold">{p.player}{p.first_deposit && <span className="ml-1 text-[10px] font-bold text-win">FTD</span>}</td>
                    <td className="text-right">{money(p.deposits)}</td><td className="text-right">{p.plays}</td><td className="text-right">{money(p.stakes)}</td>
                    <td className="text-right font-semibold">{signed(Number(p.ngr))}</td>
                  </tr>
                ))}
                {data.players.length === 0 && <tr><td colSpan={5} className="py-3 text-muted-foreground">No active players in this period.</td></tr>}
              </tbody>
            </table>
          </div>
        </>
      )}
    </div>
  );
}
