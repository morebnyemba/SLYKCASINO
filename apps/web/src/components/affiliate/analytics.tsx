'use client';

import { useEffect, useState } from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import {
  BarChart, LiveIndicator, TimeframePicker, timeframeQuery, usePolling, type TimeframeValue,
} from '@slyk/ui/components/analytics';
import { Spinner } from '@slyk/ui/components/spinner';
import { useApi } from '@/lib/use-api';

interface Product { plays: number; stakes: string; wins: string; ggr: string }
interface Kpis {
  clicks: number; signups: number; ftds: number; signup_rate: string | null; ftd_rate: string | null; referrals_total: number;
  deposits: string; deposit_count: number; withdrawals: string; net_deposits: string; depositors: number; avg_deposit: string;
  active_players: number; plays: number; stakes: string; wins: string; player_losses: string; bonuses: string; ngr: string;
  margin_percent: string | null; sportsbook: Product; casino: Product;
  revshare_percent: string; revshare_estimate: string; cpa_earned: string; commission_estimate: string; commission_paid: string;
}
interface Point { t: string; deposits: string; stakes: string; ggr: string; ngr: string; plays: number; clicks: number; signups: number; ftds: number }
interface Analytics {
  label: string; bucket: string; kpis: Kpis; series: Point[];
  campaigns: { campaign: string; clicks: number; signups: number; ftds: number; deposits: string; stakes: string; ngr: string; plays: number }[];
  players: { player: string; campaign: string; deposits: string; stakes: string; wins: string; plays: number; ngr: string; first_deposit: boolean }[];
  activity: { id: string; at: string; kind: string; amount: string | null; player: string }[];
}

const money = (v: string | number) => {
  const n = Number(v);
  return `${n < 0 ? '−' : ''}$${Math.abs(n).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
};
const count = (v: number) => Math.round(v).toLocaleString();

const METRICS: { key: keyof Point; label: string; money: boolean }[] = [
  { key: 'deposits', label: 'Deposits', money: true },
  { key: 'plays', label: 'Plays', money: false },
  { key: 'ggr', label: 'Player losses', money: true },
  { key: 'ngr', label: 'Net revenue', money: true },
  { key: 'clicks', label: 'Clicks', money: false },
  { key: 'signups', label: 'Sign-ups', money: false },
  { key: 'ftds', label: 'First deposits', money: false },
];

const ACTIVITY: Record<string, string> = {
  signup: 'signed up', deposit: 'deposited', withdrawal: 'withdrew', bet_stake: 'placed a bet', bet_payout: 'won a bet',
  casino_debit: 'played Aviator', casino_credit: 'cashed out in Aviator', bonus: 'got a bonus',
};

function Tile({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl border border-border bg-card p-3.5">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">{label}</p>
      <p className="mt-1 text-lg font-extrabold tabular-nums">{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

function Group({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2">
      <h3 className="text-xs font-bold uppercase tracking-wider text-muted-foreground">{title}</h3>
      <div className="grid grid-cols-2 gap-2.5 md:grid-cols-4">{children}</div>
    </section>
  );
}

function ago(iso: string) {
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)}m ago`;
  if (s < 86400) return `${Math.floor(s / 3600)}h ago`;
  return new Date(iso).toLocaleDateString();
}

/** The affiliate's live analytics: every KPI for any timeframe, refreshed automatically. */
export function AffiliateAnalytics() {
  const [tf, setTf] = useState<TimeframeValue>({ frame: 'today' });
  const [metric, setMetric] = useState<(typeof METRICS)[number]>(METRICS[0]);
  const { data, loading, error, refetch } = useApi<Analytics>(`/affiliates/me/analytics/?${timeframeQuery(tf)}`);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const interval = tf.frame === 'live' || tf.frame === 'today' ? 10000 : 30000;
  usePolling(refetch, interval, [refetch]);
  useEffect(() => { if (data) setUpdatedAt(Date.now()); }, [data]);

  const k = data?.kpis;
  return (
    <Card className="rounded-2xl">
      <CardHeader className="space-y-3">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <CardTitle className="text-base">Performance{data ? ` · ${data.label}` : ''}</CardTitle>
          <LiveIndicator updatedAt={updatedAt} refreshing={loading && !!data} intervalMs={interval} />
        </div>
        <TimeframePicker value={tf} onChange={setTf} />
      </CardHeader>
      <CardContent className="space-y-6">
        {!data ? (
          error ? <p className="text-sm text-destructive">Couldn’t load your analytics. <button onClick={refetch} className="underline">Retry</button></p>
            : <div className="flex justify-center py-10"><Spinner /></div>
        ) : k && (
          <>
            <Group title="Traffic">
              <Tile label="Clicks" value={count(k.clicks)} />
              <Tile label="Sign-ups" value={count(k.signups)} hint={k.signup_rate ? `${k.signup_rate}% of clicks` : undefined} />
              <Tile label="First deposits" value={count(k.ftds)} hint={k.ftd_rate ? `${k.ftd_rate}% of sign-ups` : undefined} />
              <Tile label="Players referred" value={count(k.referrals_total)} hint="all time" />
            </Group>
            <Group title="Deposits">
              <Tile label="Deposits" value={money(k.deposits)} hint={`${k.deposit_count} deposit${k.deposit_count === 1 ? '' : 's'}`} />
              <Tile label="Depositors" value={count(k.depositors)} hint={`avg ${money(k.avg_deposit)}`} />
              <Tile label="Withdrawals" value={money(k.withdrawals)} />
              <Tile label="Net deposits" value={money(k.net_deposits)} />
            </Group>
            <Group title="Play">
              <Tile label="Active players" value={count(k.active_players)} />
              <Tile label="Plays" value={count(k.plays)} hint={`${k.sportsbook.plays} sports · ${k.casino.plays} Aviator`} />
              <Tile label="Amount staked" value={money(k.stakes)} hint={`won back ${money(k.wins)}`} />
              <Tile label="Player losses" value={money(k.player_losses)} hint={k.margin_percent ? `${k.margin_percent}% of stakes` : undefined} />
            </Group>
            <Group title="Your earnings">
              <Tile label="Net revenue" value={money(k.ngr)} hint={`after ${money(k.bonuses)} bonuses`} />
              <Tile label="Revenue share" value={money(k.revshare_estimate)} hint={`${Number(k.revshare_percent)}% of net revenue (estimate)`} />
              <Tile label="CPA earned" value={money(k.cpa_earned)} />
              <Tile label="Paid to you" value={money(k.commission_paid)} hint="in this period" />
            </Group>

            <section className="space-y-3">
              <div className="flex flex-wrap gap-1.5" role="tablist" aria-label="Chart measure">
                {METRICS.map((m) => (
                  <button key={m.key} role="tab" aria-selected={metric.key === m.key} onClick={() => setMetric(m)}
                    className={`rounded-md px-2.5 py-1 text-xs font-bold ${metric.key === m.key ? 'bg-muted text-foreground' : 'text-muted-foreground hover:text-foreground'}`}>
                    {m.label}
                  </button>
                ))}
              </div>
              <BarChart
                label={metric.label} bucket={data.bucket}
                points={data.series.map((p) => ({ t: p.t, v: Number(p[metric.key]) }))}
                format={(v) => (metric.money ? money(v) : count(v))}
              />
            </section>

            <div className="grid gap-6 lg:grid-cols-2">
              <section>
                <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">Sportsbook vs Aviator</h3>
                <table className="w-full text-sm">
                  <thead className="text-left text-xs text-muted-foreground">
                    <tr><th className="py-1.5" /><th className="text-right">Plays</th><th className="text-right">Staked</th><th className="text-right">Player losses</th></tr>
                  </thead>
                  <tbody>
                    {([['Sportsbook', k.sportsbook], ['Aviator', k.casino]] as const).map(([name, p]) => (
                      <tr key={name} className="border-t border-border">
                        <td className="py-2 font-semibold">{name}</td>
                        <td className="text-right tabular-nums">{count(p.plays)}</td>
                        <td className="text-right tabular-nums">{money(p.stakes)}</td>
                        <td className="text-right tabular-nums">{money(p.ggr)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </section>
              <section>
                <h3 className="mb-2 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">Live activity</h3>
                {data.activity.length === 0 ? <p className="text-sm text-muted-foreground">No activity from your players yet.</p> : (
                  <ul className="max-h-56 space-y-1.5 overflow-y-auto pr-1 text-sm">
                    {data.activity.map((a) => (
                      <li key={a.id} className="flex items-center justify-between gap-3">
                        <span className="min-w-0 truncate"><b>{a.player}</b> {ACTIVITY[a.kind] ?? a.kind}{a.amount ? ` · ${money(a.amount)}` : ''}</span>
                        <span className="shrink-0 text-xs text-muted-foreground">{ago(a.at)}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </section>
            </div>

            <section>
              <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">Campaigns</h3>
              {data.campaigns.length === 0 ? <p className="text-sm text-muted-foreground">No traffic in this period.</p> : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[560px] text-sm">
                    <thead className="text-left text-xs text-muted-foreground">
                      <tr><th className="py-1.5">Campaign</th><th className="text-right">Clicks</th><th className="text-right">Sign-ups</th><th className="text-right">FTDs</th><th className="text-right">Deposits</th><th className="text-right">Plays</th><th className="text-right">Net revenue</th></tr>
                    </thead>
                    <tbody>
                      {data.campaigns.map((c) => (
                        <tr key={c.campaign} className="border-t border-border">
                          <td className="py-2 font-semibold">{c.campaign}</td>
                          <td className="text-right tabular-nums">{c.clicks}</td>
                          <td className="text-right tabular-nums">{c.signups}</td>
                          <td className="text-right tabular-nums">{c.ftds}</td>
                          <td className="text-right tabular-nums">{money(c.deposits)}</td>
                          <td className="text-right tabular-nums">{c.plays}</td>
                          <td className="text-right font-semibold tabular-nums">{money(c.ngr)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>

            <section>
              <h3 className="mb-2 text-xs font-bold uppercase tracking-wider text-muted-foreground">Top players this period</h3>
              {data.players.length === 0 ? <p className="text-sm text-muted-foreground">None of your players were active in this period.</p> : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[520px] text-sm">
                    <thead className="text-left text-xs text-muted-foreground">
                      <tr><th className="py-1.5">Player</th><th className="text-right">Deposits</th><th className="text-right">Plays</th><th className="text-right">Staked</th><th className="text-right">Net revenue</th></tr>
                    </thead>
                    <tbody>
                      {data.players.map((p, i) => (
                        <tr key={i} className="border-t border-border">
                          <td className="py-2 font-semibold">{p.player}{p.first_deposit && <span className="ml-1.5 rounded bg-win/15 px-1.5 py-0.5 text-[10px] font-bold text-win">FTD</span>}</td>
                          <td className="text-right tabular-nums">{money(p.deposits)}</td>
                          <td className="text-right tabular-nums">{p.plays}</td>
                          <td className="text-right tabular-nums">{money(p.stakes)}</td>
                          <td className="text-right font-semibold tabular-nums">{money(p.ngr)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </section>
          </>
        )}
      </CardContent>
    </Card>
  );
}
