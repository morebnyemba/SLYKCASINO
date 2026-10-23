'use client';

import { useMemo, useState } from 'react';
import { Panel, Tabs, TextInput, cx, money } from '@/components/console/ui';
import { useApi } from '@/lib/use-api';

interface Product { stakes: string; payouts: string; ggr: string; margin: string | null }
interface Profit {
  label: string;
  sportsbook: Product; aviator: Product;
  stakes: string; payouts: string; ggr: string; margin: string | null;
  bonuses: string; agent_commission: string; adjustments: string;
  profit: string; profit_margin: string | null;
  cash: { deposits: string; withdrawals: string; net: string };
}

type Frame = 'today' | 'yesterday' | '7d' | '30d' | 'this_month' | 'last_month' | 'this_year' | 'all' | 'custom';
const FRAMES: { id: Frame; label: string }[] = [
  { id: 'today', label: 'Today' }, { id: 'yesterday', label: 'Yesterday' }, { id: '7d', label: '7 days' },
  { id: '30d', label: '30 days' }, { id: 'this_month', label: 'This month' }, { id: 'last_month', label: 'Last month' },
  { id: 'this_year', label: 'This year' }, { id: 'all', label: 'All time' }, { id: 'custom', label: 'Dates' },
];

const signedTone = (v: string | number) => (Number(v) < 0 ? 'text-down' : 'text-win');

function Line({ label, value, hint, minus, strong }: { label: string; value: string; hint?: string; minus?: boolean; strong?: boolean }) {
  return (
    <div className={cx('flex items-baseline justify-between gap-3 py-2', strong && 'border-t border-border pt-3')}>
      <span className={cx('text-sm', strong ? 'font-bold' : 'text-muted-foreground')}>
        {label}{hint && <span className="ml-1.5 text-xs text-muted-foreground">{hint}</span>}
      </span>
      <span className={cx('tabular-nums', strong ? cx('text-lg font-extrabold', signedTone(value)) : 'font-semibold')}>
        {minus && Number(value) !== 0 ? '− ' : ''}{money(value)}
      </span>
    </div>
  );
}

/** What the house made in a period: GGR per product, less bonuses and agent commission, plus cash in and out. */
export function ProfitPanel() {
  const today = useMemo(() => new Date().toISOString().slice(0, 10), []);
  const [frame, setFrame] = useState<Frame>('today');
  const [from, setFrom] = useState(today);
  const [to, setTo] = useState(today);
  const query = frame === 'custom'
    ? (from && to ? `frame=custom&start=${from}&end=${to}` : null)
    : `frame=${frame}`;
  const { data: p, loading } = useApi<Profit>(query ? `/admin/profit/?${query}` : null);
  const pct = (v: string | null) => (v == null ? '—' : `${v}%`);

  return (
    <Panel
      title="Profit"
      description={p ? `${p.label}: gross gaming revenue less bonuses and agent commission.` : 'Gross gaming revenue less bonuses and agent commission.'}
    >
      <div className="space-y-4">
        <Tabs value={frame} onChange={setFrame} items={FRAMES} />
        {frame === 'custom' && (
          <div className="flex flex-wrap items-center gap-2 text-sm">
            <span className="text-muted-foreground">From</span>
            <TextInput type="date" value={from} max={to || today} onChange={(e) => setFrom(e.target.value)} className="w-auto" />
            <span className="text-muted-foreground">to</span>
            <TextInput type="date" value={to} min={from} max={today} onChange={(e) => setTo(e.target.value)} className="w-auto" />
          </div>
        )}

        {!p ? (
          <div className="h-48 animate-pulse rounded-xl bg-muted/50" />
        ) : (
          <div className={cx('grid gap-5 lg:grid-cols-[1.3fr_1fr]', loading && 'opacity-60')}>
            <div>
              <div className="mb-3 grid grid-cols-2 gap-3">
                <div className="rounded-xl bg-muted/40 p-3">
                  <p className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">Net profit</p>
                  <p className={cx('text-2xl font-extrabold tabular-nums', signedTone(p.profit))}>{money(p.profit)}</p>
                  <p className="text-xs text-muted-foreground">{pct(p.profit_margin)} of stakes</p>
                </div>
                <div className="rounded-xl bg-muted/40 p-3">
                  <p className="text-[11px] font-bold uppercase tracking-wide text-muted-foreground">GGR</p>
                  <p className={cx('text-2xl font-extrabold tabular-nums', signedTone(p.ggr))}>{money(p.ggr)}</p>
                  <p className="text-xs text-muted-foreground">{pct(p.margin)} hold</p>
                </div>
              </div>
              <Line label="Stakes" value={p.stakes} />
              <Line label="Payouts to players" value={p.payouts} minus />
              <Line label="Bonuses given" value={p.bonuses} minus />
              <Line label="Agent commission" value={p.agent_commission} minus />
              <Line label="Net profit" value={p.profit} strong />
              {Number(p.adjustments) !== 0 && (
                <p className="text-xs text-muted-foreground">Manual balance adjustments in this period: {money(p.adjustments)} (not counted above).</p>
              )}
            </div>
            <div className="space-y-3">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr><th className="pb-1 font-medium">Product</th><th className="pb-1 text-right font-medium">Stakes</th><th className="pb-1 text-right font-medium">GGR</th><th className="pb-1 text-right font-medium">Hold</th></tr>
                </thead>
                <tbody className="tabular-nums">
                  {([['Sportsbook', p.sportsbook], ['Aviator', p.aviator]] as const).map(([name, x]) => (
                    <tr key={name} className="border-t border-border">
                      <td className="py-2 font-semibold">{name}</td>
                      <td className="py-2 text-right">{money(x.stakes)}</td>
                      <td className={cx('py-2 text-right font-semibold', signedTone(x.ggr))}>{money(x.ggr)}</td>
                      <td className="py-2 text-right text-muted-foreground">{pct(x.margin)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <div className="rounded-xl border border-border p-3">
                <p className="mb-1 text-xs font-bold uppercase tracking-wide text-muted-foreground">Cash</p>
                <Line label="Deposits" value={p.cash.deposits} />
                <Line label="Withdrawals paid" value={p.cash.withdrawals} minus />
                <Line label="Net cash in" value={p.cash.net} strong />
              </div>
            </div>
          </div>
        )}
      </div>
    </Panel>
  );
}
