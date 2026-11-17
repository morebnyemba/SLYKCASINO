'use client';

import Link from 'next/link';
import type { IconType } from 'react-icons';
import { BsArrowRight, BsDiagram3, BsPeople, BsPieChart } from 'react-icons/bs';
import { Panel, cx, money } from '@/components/console/ui';
import { useApi } from '@/lib/use-api';

interface Owed {
  total: string;
  players: {
    total: string; people: number; winnings: string; deposit: string; deposit_after_fee: string; deposit_fee_percent: string;
    withdrawals_waiting: string; withdrawals_waiting_count: number; players_with_cash: number;
    bonus: string; aviator_bonus_profit: string;
  };
  agents: {
    total: string; people: number; available: string; locked: string; in_payout: string; pending_approval: string;
    owed_by_agents: string; agents_with_money: number;
  };
  partners: null | {
    total: string; people: number; balances: string; withdrawals_waiting: string;
    wallets: { slot: number; label: string; holder: string | null; balance: string; withdrawal_waiting: string }[];
  };
}

const people = (n: number) => `${n.toLocaleString()} ${n === 1 ? 'person' : 'people'}`;

function Row({ label, value, hint, muted }: { label: string; value: string; hint?: string; muted?: boolean }) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-1.5 text-sm">
      <span className={cx(muted ? 'text-muted-foreground/80' : 'text-muted-foreground')}>
        {label}{hint && <span className="ml-1 text-xs text-muted-foreground/70">{hint}</span>}
      </span>
      <span className={cx('tabular-nums font-semibold', muted && 'text-muted-foreground')}>{money(value)}</span>
    </div>
  );
}

function OwedCard({ icon: Icon, title, total, sub, href, children, footer }: {
  icon: IconType; title: string; total: string; sub: string; href: string; children: React.ReactNode; footer?: React.ReactNode;
}) {
  return (
    <div className="flex flex-col rounded-2xl border border-border/70 bg-card p-4">
      <div className="flex items-center gap-2">
        <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-secondary/15 text-secondary"><Icon size={16} /></span>
        <p className="flex-1 text-sm font-bold">{title}</p>
        <Link href={href} className="text-muted-foreground hover:text-foreground" aria-label={`Open ${title}`}><BsArrowRight /></Link>
      </div>
      <p className="mt-3 text-2xl font-extrabold tabular-nums">{money(total)}</p>
      <p className="text-xs text-muted-foreground">{sub}</p>
      <div className="mt-3 divide-y divide-border/50 border-t border-border/60">{children}</div>
      {footer && <div className="mt-auto pt-3 text-xs text-muted-foreground">{footer}</div>}
    </div>
  );
}

/** Everything the business owes right now: players, agents and (for revenue-share viewers) partners. */
export function MoneyOwedPanel() {
  const { data: o, loading, error } = useApi<Owed>('/admin/liabilities/');
  if (error) return null;
  const p = o?.players;
  const a = o?.agents;
  const part = o?.partners;
  return (
    <Panel
      title="Money owed"
      description="What the business owes right now, from live balances. Bonus money isn’t cash owed until a player wins it into Winnings."
      actions={o && <span className="text-sm font-bold">Total <span className="tabular-nums text-lg font-extrabold">{money(o.total)}</span></span>}
    >
      {loading && !o ? <p className="text-sm text-muted-foreground">Loading…</p> : o && p && a && (
        <div className={cx('grid gap-4', part ? 'lg:grid-cols-3' : 'lg:grid-cols-2')}>
          <OwedCard icon={BsPeople} title="Players" total={p.total} href="/money-owed?tab=players"
            sub={`Owed to ${people(p.people)}`}
            footer={<>Not cash yet: Bonus {money(p.bonus)} · unclaimed Aviator bonus profit {money(p.aviator_bonus_profit)}</>}>
            <Row label="Winnings wallets" value={p.winnings} hint="withdrawable" />
            <Row label="Deposit wallets" value={p.deposit} hint={`${money(p.deposit_after_fee)} after the ${Number(p.deposit_fee_percent)}% fee`} />
            <Row label="Withdrawals waiting" value={p.withdrawals_waiting}
              hint={`${p.withdrawals_waiting_count} to send, after fees`} />
          </OwedCard>
          <OwedCard icon={BsDiagram3} title="Agents" total={a.total} href="/money-owed?tab=agents"
            sub={`Owed to ${people(a.people)}`}
            footer={<>
              Waiting for approval: {money(a.pending_approval)}
              {Number(a.owed_by_agents) > 0 && <> · Agents owe back {money(a.owed_by_agents)} (netted off future commissions)</>}
            </>}>
            <Row label="Free to withdraw" value={a.available} />
            <Row label="Locked until month end" value={a.locked} />
            <Row label="Payouts being sent" value={a.in_payout} />
          </OwedCard>
          {part && (
            <OwedCard icon={BsPieChart} title="Partners" total={part.total} href="/money-owed?tab=partners"
              sub={`Owed to ${people(part.people)}`}
              footer={part.wallets.length > 0 && (
                <span>{part.wallets.map((w) => `${w.holder ?? w.label} ${money(Number(w.balance) + Number(w.withdrawal_waiting))}`).join(' · ')}</span>
              )}>
              <Row label="Wallet balances" value={part.balances} />
              <Row label="Withdrawals waiting" value={part.withdrawals_waiting} />
            </OwedCard>
          )}
        </div>
      )}
    </Panel>
  );
}
