'use client';

import Link from 'next/link';
import type { IconType } from 'react-icons';
import {
  BsArrowRight, BsBroadcast, BsCalendar2Week, BsCashCoin, BsCashStack, BsDiagram3, BsGraphUpArrow, BsGrid1X2,
  BsPersonBadge, BsPersonPlus, BsReceipt, BsTicketPerforated, BsWallet2, BsExclamationTriangle,
} from 'react-icons/bs';
import { RealtimeFeed } from '@/components/realtime-feed';
import { Badge, Panel, PageHeader, StatTile, cx, money } from '@/components/console/ui';
import { useApi } from '@/lib/use-api';

interface Stats {
  today?: { deposits: string; withdrawals: string; stakes: string; payouts: string; ggr: string; bonuses: string; new_players: number };
  players?: { total: number; verified: number; suspended: number };
  queues?: { kyc_pending: number; payments_pending: number; affiliates_pending: number; commissions_pending: number; markets_to_settle: number };
  sportsbook?: { live: number; upcoming: number; unpriced: number; open_bets: number; open_slips: number };
  week?: { day: string; deposits: string; ggr: string }[];
  open_chats?: number;
}

/** Seven-day deposits vs GGR as paired bars. */
function WeekChart({ week }: { week: NonNullable<Stats['week']> }) {
  const values = week.flatMap((d) => [Number(d.deposits), Math.abs(Number(d.ggr))]);
  const max = Math.max(1, ...values);
  return (
    <div>
      <div className="flex h-44 items-end gap-3">
        {week.map((d) => {
          const dep = Number(d.deposits);
          const ggr = Number(d.ggr);
          const label = new Date(`${d.day}T00:00:00`).toLocaleDateString(undefined, { weekday: 'short' });
          return (
            <div key={d.day} className="flex h-full flex-1 flex-col items-center gap-2">
              <div className="flex w-full flex-1 items-end justify-center gap-1">
                <div
                  title={`Deposits ${money(dep)}`}
                  className="w-1/2 max-w-5 rounded-t-md bg-gradient-to-t from-secondary/70 to-secondary"
                  style={{ height: `${Math.max(2, (dep / max) * 100)}%` }}
                />
                <div
                  title={`GGR ${money(ggr)}`}
                  className={cx('w-1/2 max-w-5 rounded-t-md', ggr < 0 ? 'bg-live/70' : 'bg-gradient-to-t from-win/60 to-win')}
                  style={{ height: `${Math.max(2, (Math.abs(ggr) / max) * 100)}%` }}
                />
              </div>
              <span className="text-[11px] font-semibold text-muted-foreground">{label}</span>
            </div>
          );
        })}
      </div>
      <div className="mt-4 flex gap-4 text-xs text-muted-foreground">
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-secondary" />Deposits</span>
        <span className="flex items-center gap-1.5"><span className="h-2.5 w-2.5 rounded-sm bg-win" />Gross gaming revenue</span>
      </div>
    </div>
  );
}

function QueueRow({ icon: Icon, label, count, href, hint }: {
  icon: IconType; label: string; count: number; href: string; hint: string;
}) {
  const hot = count > 0;
  return (
    <Link
      href={href}
      className="group flex items-center gap-3.5 rounded-xl border border-border/60 bg-background/40 px-4 py-3 transition-colors hover:border-secondary/50 hover:bg-muted/40"
    >
      <span className={cx('flex h-10 w-10 shrink-0 items-center justify-center rounded-xl', hot ? 'bg-gold/15 text-gold' : 'bg-muted text-muted-foreground')}>
        <Icon size={16} />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold">{label}</span>
        <span className="block truncate text-xs text-muted-foreground">{hint}</span>
      </span>
      <span className={cx('text-xl font-extrabold tabular-nums', hot ? 'text-foreground' : 'text-muted-foreground/60')}>{count}</span>
      <BsArrowRight className="text-muted-foreground transition-transform group-hover:translate-x-0.5" size={14} />
    </Link>
  );
}

export default function DashboardPage() {
  const { data: s, loading } = useApi<Stats>('/admin/stats/');
  const t = s?.today;
  const q = s?.queues;
  const sb = s?.sportsbook;
  const attention = (q?.kyc_pending ?? 0) + (q?.markets_to_settle ?? 0) + (q?.commissions_pending ?? 0) + (q?.affiliates_pending ?? 0);
  const date = new Date().toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' });

  return (
    <div className="space-y-6">
      <PageHeader
        icon={BsGrid1X2}
        eyebrow={date}
        title="Operations dashboard"
        description="Today's money, what needs a person, and the sportsbook at a glance."
        actions={attention > 0 ? <Badge tone="gold" dot>{attention} item{attention === 1 ? ' needs' : 's need'} attention</Badge> : <Badge tone="green" dot>All queues clear</Badge>}
      />

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-3 xl:grid-cols-6">
        <StatTile loading={loading} icon={BsWallet2} tone="indigo" label="Deposits today" value={money(t?.deposits)} href="/transactions" />
        <StatTile loading={loading} icon={BsCashStack} tone="slate" label="Withdrawals" value={money(t?.withdrawals)} href="/transactions" />
        <StatTile loading={loading} icon={BsReceipt} tone="indigo" label="Stakes" value={money(t?.stakes)} />
        <StatTile loading={loading} icon={BsCashCoin} tone="gold" label="Payouts" value={money(t?.payouts)} />
        <StatTile
          loading={loading} icon={BsGraphUpArrow} tone={Number(t?.ggr ?? 0) < 0 ? 'red' : 'green'} label="GGR today" value={money(t?.ggr)}
          hint={t ? `Bonuses paid ${money(t.bonuses)}` : undefined}
        />
        <StatTile
          loading={loading} icon={BsPersonPlus} tone="green" label="New players" value={t?.new_players ?? 0} href="/users"
          hint={s?.players ? `${s.players.total.toLocaleString()} total · ${s.players.verified} verified` : undefined}
        />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.6fr_1fr]">
        <Panel title="Last 7 days" description="Deposits and gross gaming revenue (stakes minus payouts), sportsbook and casino.">
          {s?.week ? <WeekChart week={s.week} /> : <div className="h-44 animate-pulse rounded-xl bg-muted/50" />}
        </Panel>
        <Panel title="Needs attention" description="Queues waiting on a person.">
          <div className="space-y-2.5">
            <QueueRow icon={BsPersonBadge} label="KYC documents" count={q?.kyc_pending ?? 0} href="/kyc" hint="Identity checks waiting for review" />
            <QueueRow icon={BsExclamationTriangle} label="Markets to settle" count={q?.markets_to_settle ?? 0} href="/sportsbook/matches?state=finished" hint="Finished matches the feed couldn't settle" />
            <QueueRow icon={BsDiagram3} label="Affiliate commissions" count={q?.commissions_pending ?? 0} href="/affiliates" hint={`${q?.affiliates_pending ?? 0} affiliate applications pending`} />
            <QueueRow icon={BsWallet2} label="Payments in progress" count={q?.payments_pending ?? 0} href="/transactions" hint="Paynow deposits awaiting confirmation" />
          </div>
        </Panel>
      </div>

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile loading={loading} icon={BsBroadcast} tone="red" label="Live now" value={sb?.live ?? 0} href="/sportsbook/matches?state=live" hint="Matches in play" />
        <StatTile loading={loading} icon={BsCalendar2Week} tone="indigo" label="Upcoming, priced" value={sb?.upcoming ?? 0} href="/sportsbook/matches" />
        <StatTile loading={loading} icon={BsExclamationTriangle} tone="gold" label="Awaiting odds" value={sb?.unpriced ?? 0} href="/sportsbook/matches?state=unpriced" hint="Hidden from players until priced" />
        <StatTile loading={loading} icon={BsTicketPerforated} tone="slate" label="Open bets" value={(sb?.open_bets ?? 0) + (sb?.open_slips ?? 0)} href="/betting-feeds" hint={sb ? `${sb.open_bets} singles · ${sb.open_slips} multiples` : undefined} />
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        <RealtimeFeed channel="admin:bets" title="Live bet stream" height={260} />
        <RealtimeFeed channel="admin:chat" title="Incoming chats" height={260} />
      </div>
    </div>
  );
}
