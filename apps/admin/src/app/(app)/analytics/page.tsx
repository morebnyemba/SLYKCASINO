'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import {
  BsActivity, BsAirplane, BsBroadcast, BsCashCoin, BsCashStack, BsDiagram3,
  BsGraphUpArrow, BsPeople, BsPersonPlus, BsPieChart, BsReceipt, BsTicketPerforated, BsWallet2,
} from 'react-icons/bs';
import {
  BarChart, LiveIndicator, TimeframePicker, timeframeQuery, usePolling, type TimeframeValue,
} from '@slyk/ui/components/analytics';
import { Badge, PageHeader, Panel, StatTile, cx, money, tableClass, tdClass, thClass, trClass } from '@/components/console/ui';
import { useApi } from '@/lib/use-api';

interface Product { plays: number; stakes: string; wins: string; ggr: string }
interface Kpis {
  deposits: string; deposit_count: number; withdrawals: string; withdrawal_count: number; net_deposits: string;
  depositors: number; ftds: number; ftd_rate: string | null; signups: number; active_players: number; plays: number;
  stakes: string; wins: string; ggr: string; bonuses: string; ngr: string; margin_percent: string | null; avg_deposit: string;
  sportsbook: Product; casino: Product;
  affiliate: { deposits: string; ngr: string; active_players: number; signups: number };
}
interface Point { t: string; deposits: string; withdrawals: string; stakes: string; ggr: string; ngr: string; plays: number; signups: number; ftds: number }
interface Analytics {
  label: string; bucket: string; kpis: Kpis; series: Point[];
  activity: { id: number; at: string; kind: string; amount: string; player: string }[];
  right_now: {
    last_hour: { deposits: string; plays: number; stakes: string; ggr: string; active_players: number };
    live_matches: number; open_bets: number; signups_last_hour: number;
    aviator: { round: number | null; status: string | null; players: number };
  };
  top_affiliates: { id: number; code: string; owner: string; active_players: number; plays: number; deposits: string; stakes: string; ngr: string }[];
}

const count = (v: number) => Math.round(v).toLocaleString();
const METRICS: { key: keyof Point; label: string; money: boolean }[] = [
  { key: 'deposits', label: 'Deposits', money: true },
  { key: 'withdrawals', label: 'Withdrawals', money: true },
  { key: 'stakes', label: 'Turnover', money: true },
  { key: 'ggr', label: 'GGR', money: true },
  { key: 'ngr', label: 'NGR', money: true },
  { key: 'plays', label: 'Bets placed', money: false },
  { key: 'signups', label: 'Sign-ups', money: false },
  { key: 'ftds', label: 'First deposits', money: false },
];
const KIND: Record<string, { label: string; tone: 'green' | 'red' | 'gold' | 'indigo' | 'slate' }> = {
  deposit: { label: 'Deposit', tone: 'green' }, withdrawal: { label: 'Withdrawal', tone: 'gold' },
  bet_stake: { label: 'Sports bet', tone: 'indigo' }, bet_payout: { label: 'Sports win', tone: 'slate' },
  casino_debit: { label: 'Aviator bet', tone: 'indigo' }, casino_credit: { label: 'Aviator win', tone: 'slate' },
  bonus: { label: 'Bonus', tone: 'gold' },
};
const signedMoney = (v: number) => (v < 0 ? `−${money(-v)}` : money(v));

/** Platform analytics for any timeframe, refreshing live. */
export default function AnalyticsPage() {
  const [tf, setTf] = useState<TimeframeValue>({ frame: 'today' });
  const [metric, setMetric] = useState(METRICS[0]);
  const { data, loading, error, refetch } = useApi<Analytics>(`/admin/analytics/?${timeframeQuery(tf)}`);
  const [updatedAt, setUpdatedAt] = useState<number | null>(null);
  const interval = tf.frame === 'live' || tf.frame === 'today' ? 5000 : 20000;
  usePolling(refetch, interval, [refetch]);
  useEffect(() => { if (data) setUpdatedAt(Date.now()); }, [data]);
  const k = data?.kpis;
  const rn = data?.right_now;
  const first = !data;

  return (
    <div className="space-y-6">
      <PageHeader
        icon={BsPieChart} eyebrow="Reports" title="Analytics"
        description="Every figure comes straight from the wallet ledger and updates live — pick any timeframe, up to all time."
        actions={<LiveIndicator updatedAt={updatedAt} refreshing={loading && !!data} intervalMs={interval} />}
      />
      <TimeframePicker value={tf} onChange={setTf} />
      {error && !data && <p className="text-sm text-live">Couldn’t load analytics: {error}</p>}

      <Panel title="Right now" description="The last 60 minutes, whatever timeframe is selected.">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4 xl:grid-cols-7">
          {[
            ['Deposits', rn ? money(rn.last_hour.deposits) : ''],
            ['Bets placed', rn ? count(rn.last_hour.plays) : ''],
            ['Turnover', rn ? money(rn.last_hour.stakes) : ''],
            ['GGR', rn ? signedMoney(Number(rn.last_hour.ggr)) : ''],
            ['Players active', rn ? count(rn.last_hour.active_players) : ''],
            ['Live matches', rn ? `${rn.live_matches} · ${rn.open_bets} open bets` : ''],
            ['Aviator', rn?.aviator.round ? `#${rn.aviator.round} ${rn.aviator.status} · ${rn.aviator.players} in` : '—'],
          ].map(([label, value]) => (
            <div key={label} className="rounded-xl bg-muted/40 px-3 py-2.5">
              <p className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">{label}</p>
              <p className="mt-0.5 font-extrabold tabular-nums">{first ? <span className="inline-block h-5 w-14 animate-pulse rounded bg-muted" /> : value}</p>
            </div>
          ))}
        </div>
      </Panel>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile loading={first} icon={BsWallet2} tone="green" label="Deposits" value={money(k?.deposits)}
          hint={k && `${k.deposit_count} deposits · ${k.depositors} depositors · avg ${money(k.avg_deposit)}`} />
        <StatTile loading={first} icon={BsCashStack} tone="gold" label="Withdrawals" value={money(k?.withdrawals)}
          hint={k && `${k.withdrawal_count} paid · net deposits ${signedMoney(Number(k.net_deposits))}`} />
        <StatTile loading={first} icon={BsGraphUpArrow} tone={Number(k?.ggr ?? 0) < 0 ? 'red' : 'green'} label="GGR (player losses)"
          value={signedMoney(Number(k?.ggr ?? 0))} hint={k && `${k.margin_percent ?? '—'}% hold on ${money(k.stakes)} turnover`} />
        <StatTile loading={first} icon={BsCashCoin} tone={Number(k?.ngr ?? 0) < 0 ? 'red' : 'indigo'} label="NGR"
          value={signedMoney(Number(k?.ngr ?? 0))} hint={k && `after ${money(k.bonuses)} bonuses`} />
        <StatTile loading={first} icon={BsReceipt} tone="indigo" label="Bets placed" value={count(k?.plays ?? 0)}
          hint={k && `${k.sportsbook.plays} sports · ${k.casino.plays} Aviator`} />
        <StatTile loading={first} icon={BsPeople} tone="slate" label="Active players" value={count(k?.active_players ?? 0)} />
        <StatTile loading={first} icon={BsPersonPlus} tone="indigo" label="Sign-ups" value={count(k?.signups ?? 0)}
          hint={k && `${k.ftds} first deposits${k.ftd_rate ? ` · ${k.ftd_rate}% converted` : ''}`} />
        <StatTile loading={first} icon={BsDiagram3} tone="gold" label="From affiliates" value={money(k?.affiliate.deposits)}
          hint={k && `deposits · ${k.affiliate.signups} sign-ups · NGR ${signedMoney(Number(k.affiliate.ngr))}`} />
      </div>

      <Panel title={`Over time${data ? ` · ${data.label}` : ''}`} description="One measure at a time — hover a bar for its value, or switch to the table.">
        <div className="mb-4 flex flex-wrap gap-1.5">
          {METRICS.map((m) => (
            <button key={m.key} onClick={() => setMetric(m)}
              className={cx('rounded-lg px-3 py-1.5 text-xs font-bold', metric.key === m.key ? 'bg-secondary text-secondary-foreground' : 'bg-muted/60 text-muted-foreground hover:text-foreground')}>
              {m.label}
            </button>
          ))}
        </div>
        {data ? (
          <BarChart label={metric.label} bucket={data.bucket} height={240}
            points={data.series.map((p) => ({ t: p.t, v: Number(p[metric.key]) }))}
            format={(v) => (metric.money ? signedMoney(v) : count(v))} />
        ) : <div className="h-60 animate-pulse rounded-xl bg-muted/50" />}
      </Panel>

      <div className="grid gap-6 xl:grid-cols-[1.1fr_1fr]">
        <Panel title="Sportsbook vs Aviator" padded={false}>
          <table className={tableClass}>
            <thead><tr><th className={thClass}>Product</th><th className={thClass}>Bets</th><th className={thClass}>Turnover</th><th className={thClass}>Paid out</th><th className={thClass}>GGR</th><th className={thClass}>Hold</th></tr></thead>
            <tbody>
              {k && ([['Sportsbook', BsTicketPerforated, k.sportsbook], ['Aviator', BsAirplane, k.casino]] as const).map(([name, Icon, p]) => (
                <tr key={name} className={trClass}>
                  <td className={cx(tdClass, 'font-semibold')}><span className="inline-flex items-center gap-2"><Icon className="text-muted-foreground" />{name}</span></td>
                  <td className={cx(tdClass, 'tabular-nums')}>{count(p.plays)}</td>
                  <td className={cx(tdClass, 'tabular-nums')}>{money(p.stakes)}</td>
                  <td className={cx(tdClass, 'tabular-nums')}>{money(p.wins)}</td>
                  <td className={cx(tdClass, 'font-semibold tabular-nums', Number(p.ggr) < 0 ? 'text-live' : 'text-win')}>{signedMoney(Number(p.ggr))}</td>
                  <td className={cx(tdClass, 'tabular-nums text-muted-foreground')}>{Number(p.stakes) > 0 ? `${(Number(p.ggr) / Number(p.stakes) * 100).toFixed(1)}%` : '—'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>

        <Panel title="Live activity" description="The latest money movements across the site." actions={<BsBroadcast className="text-win" />}>
          {data && data.activity.length === 0 && <p className="text-sm text-muted-foreground">Nothing yet.</p>}
          <ul className="max-h-72 space-y-1.5 overflow-y-auto pr-1 text-sm">
            {data?.activity.map((a) => {
              const kind = KIND[a.kind] ?? { label: a.kind, tone: 'slate' as const };
              return (
                <li key={a.id} className="flex items-center gap-3">
                  <Badge tone={kind.tone} className="w-24 justify-center">{kind.label}</Badge>
                  <span className="min-w-0 flex-1 truncate font-semibold">{a.player}</span>
                  <span className="tabular-nums">{money(a.amount)}</span>
                  <span className="w-16 text-right text-xs text-muted-foreground">{new Date(a.at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</span>
                </li>
              );
            })}
          </ul>
        </Panel>
      </div>

      <Panel title="Top affiliates" description="Ranked by their players’ net revenue in this period." padded={false}
        actions={<Link href="/affiliates" className="text-xs font-semibold text-secondary hover:underline">All affiliates</Link>}>
        <div className="overflow-x-auto">
          <table className={tableClass}>
            <thead><tr><th className={thClass}>Code</th><th className={thClass}>Owner</th><th className={thClass}>Active players</th><th className={thClass}>Bets</th><th className={thClass}>Deposits</th><th className={thClass}>Turnover</th><th className={thClass}>NGR</th></tr></thead>
            <tbody>
              {data?.top_affiliates.map((a) => (
                <tr key={a.id} className={trClass}>
                  <td className={cx(tdClass, 'font-mono font-bold')}>{a.code}</td>
                  <td className={tdClass}>{a.owner}</td>
                  <td className={cx(tdClass, 'tabular-nums')}>{a.active_players}</td>
                  <td className={cx(tdClass, 'tabular-nums')}>{count(a.plays)}</td>
                  <td className={cx(tdClass, 'tabular-nums')}>{money(a.deposits)}</td>
                  <td className={cx(tdClass, 'tabular-nums')}>{money(a.stakes)}</td>
                  <td className={cx(tdClass, 'font-semibold tabular-nums', Number(a.ngr) < 0 ? 'text-live' : 'text-win')}>{signedMoney(Number(a.ngr))}</td>
                </tr>
              ))}
              {data && data.top_affiliates.length === 0 && (
                <tr><td colSpan={7} className="px-4 py-8 text-center text-sm text-muted-foreground">No affiliate players were active in this period.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      </Panel>
      <p className="flex items-start gap-2 text-xs text-muted-foreground">
        <BsActivity className="mt-0.5 shrink-0" />
        Turnover is the amount staked; GGR is turnover minus winnings and refunds (what players lost); NGR is GGR minus bonuses.
      </p>
    </div>
  );
}
