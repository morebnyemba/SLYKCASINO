'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { BsJournalText } from 'react-icons/bs';
import {
  EmptyState, PageHeader, Pager, Panel, Tabs, TextInput, cx, money, tableClass, tdClass, thClass, trClass,
} from '@/components/console/ui';
import { useApi } from '@/lib/use-api';

type Tab = 'players' | 'agents' | 'partners';

interface Summary {
  total: string;
  players: { total: string; people: number };
  agents: { total: string; people: number };
  partners: null | { total: string; people: number };
}
interface PlayerRow {
  player_id: number; username: string; winnings: string; deposit: string; withdrawals_waiting: string; total: string;
  bonus: string; aviator_bonus_profit: string;
}
interface AgentRow {
  affiliate_id: number; code: string; username: string; status: string; available: string; locked: string;
  in_payout: string; pending_approval: string; owes_back: string; total: string;
}
interface PartnerRow { slot: number; label: string; holder: string | null; balance: string; withdrawal_waiting: string; total: string }
interface List<T> { count: number; total: string; results: T[]; page?: number; page_size?: number }

const people = (n: number) => `${n.toLocaleString()} ${n === 1 ? 'person' : 'people'}`;
const num = (v: string) => <span className={cx('tabular-nums', Number(v) === 0 && 'text-muted-foreground/60')}>{money(v)}</span>;

function Head({ count, total, search }: { count: number; total: string; search?: string }) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-6 gap-y-1 px-4 py-3 text-sm">
      <span><b className="tabular-nums">{people(count)}</b> owed{search ? <> (matching “{search}”)</> : null}</span>
      <span>Total <b className="tabular-nums text-base">{money(total)}</b></span>
    </div>
  );
}

function Players() {
  const [q, setQ] = useState('');
  const [search, setSearch] = useState('');
  const [page, setPage] = useState(1);
  useEffect(() => { const t = setTimeout(() => { setSearch(q.trim()); setPage(1); }, 300); return () => clearTimeout(t); }, [q]);
  const { data, loading } = useApi<List<PlayerRow>>(`/admin/liabilities/players/?page=${page}&page_size=50${search ? `&q=${encodeURIComponent(search)}` : ''}`);
  return (
    <Panel title="Players owed" padded={false}
      description="Winnings and Deposit balances, and withdrawals requested but not yet sent (after fees). Bonus money and unclaimed Aviator bonus profit are shown but not counted."
      actions={<div className="w-56"><TextInput value={q} onChange={(e) => setQ(e.target.value)} placeholder="Search username" className="h-9 text-sm" /></div>}>
      {data && <Head count={data.count} total={data.total} search={search} />}
      {loading && !data ? <p className="px-4 py-6 text-sm text-muted-foreground">Loading…</p>
        : !data || data.results.length === 0 ? <EmptyState icon={BsJournalText} title="Nobody is owed money" /> : (
          <div className="overflow-x-auto">
            <table className={tableClass}>
              <thead><tr>
                <th className={thClass}>Player</th><th className={thClass}>Winnings</th><th className={thClass}>Deposit</th>
                <th className={thClass}>Withdrawal waiting</th><th className={thClass}>Owed</th>
                <th className={thClass}>Not cash yet</th>
              </tr></thead>
              <tbody>
                {data.results.map((r) => (
                  <tr key={r.player_id} className={trClass}>
                    <td className={tdClass}><Link href={`/players/${r.player_id}`} className="font-semibold hover:underline">{r.username}</Link></td>
                    <td className={tdClass}>{num(r.winnings)}</td>
                    <td className={tdClass}>{num(r.deposit)}</td>
                    <td className={tdClass}>{num(r.withdrawals_waiting)}</td>
                    <td className={cx(tdClass, 'font-bold')}>{money(r.total)}</td>
                    <td className={cx(tdClass, 'text-xs text-muted-foreground')}>
                      {Number(r.bonus) > 0 || Number(r.aviator_bonus_profit) > 0
                        ? `Bonus ${money(r.bonus)} · Aviator profit ${money(r.aviator_bonus_profit)}` : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            <Pager page={page} count={data.count} pageSize={data.page_size ?? 50} onPage={setPage} />
          </div>
        )}
    </Panel>
  );
}

function Agents() {
  const { data, loading } = useApi<List<AgentRow>>('/admin/liabilities/agents/');
  return (
    <Panel title="Agents owed" padded={false}
      description="Approved commission not yet paid out (free to withdraw or locked until month end) and payouts being sent. Commission waiting for approval and amounts an agent owes back are shown but not counted.">
      {data && <Head count={data.count} total={data.total} />}
      {loading && !data ? <p className="px-4 py-6 text-sm text-muted-foreground">Loading…</p>
        : !data || data.results.length === 0 ? <EmptyState icon={BsJournalText} title="No agent is owed commission" /> : (
          <div className="overflow-x-auto">
            <table className={tableClass}>
              <thead><tr>
                <th className={thClass}>Agent</th><th className={thClass}>Free to withdraw</th><th className={thClass}>Locked</th>
                <th className={thClass}>Being sent</th><th className={thClass}>Owed</th>
                <th className={thClass}>Waiting approval</th><th className={thClass}>Owes back</th>
              </tr></thead>
              <tbody>
                {data.results.map((r) => (
                  <tr key={r.affiliate_id} className={trClass}>
                    <td className={tdClass}>
                      <Link href="/affiliates" className="font-semibold hover:underline">{r.code}</Link>
                      <p className="text-xs text-muted-foreground">{r.username}{r.status !== 'active' ? ` · ${r.status}` : ''}</p>
                    </td>
                    <td className={tdClass}>{num(r.available)}</td>
                    <td className={tdClass}>{num(r.locked)}</td>
                    <td className={tdClass}>{num(r.in_payout)}</td>
                    <td className={cx(tdClass, 'font-bold')}>{money(r.total)}</td>
                    <td className={tdClass}>{num(r.pending_approval)}</td>
                    <td className={cx(tdClass, Number(r.owes_back) > 0 && 'text-down')}>{num(r.owes_back)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
    </Panel>
  );
}

function Partners() {
  const { data, loading, error } = useApi<List<PartnerRow>>('/admin/liabilities/partners/');
  return (
    <Panel title="Partners owed" padded={false} description="Revenue-share wallet balances and withdrawals requested but not yet paid.">
      {error ? <p className="px-4 py-6 text-sm text-muted-foreground">Only people who may see the revenue share can see partners.</p> : (
        <>
          {data && <Head count={data.count} total={data.total} />}
          {loading && !data ? <p className="px-4 py-6 text-sm text-muted-foreground">Loading…</p>
            : !data || data.results.length === 0 ? <EmptyState icon={BsJournalText} title="No partner wallets" /> : (
              <div className="overflow-x-auto">
                <table className={tableClass}>
                  <thead><tr>
                    <th className={thClass}>Partner</th><th className={thClass}>Wallet balance</th>
                    <th className={thClass}>Withdrawal waiting</th><th className={thClass}>Owed</th>
                  </tr></thead>
                  <tbody>
                    {data.results.map((r) => (
                      <tr key={r.slot} className={trClass}>
                        <td className={tdClass}>
                          <Link href="/revenue-share" className="font-semibold hover:underline">{r.holder ?? 'No holder'}</Link>
                          <p className="text-xs text-muted-foreground">{r.label} · wallet {r.slot}</p>
                        </td>
                        <td className={tdClass}>{num(r.balance)}</td>
                        <td className={tdClass}>{num(r.withdrawal_waiting)}</td>
                        <td className={cx(tdClass, 'font-bold')}>{money(r.total)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
        </>
      )}
    </Panel>
  );
}

export default function MoneyOwedPage() {
  const [tab, setTab] = useState<Tab>('players');
  // ?tab= from the dashboard cards (read on mount: no Suspense boundary needed for useSearchParams).
  useEffect(() => {
    const t = new URLSearchParams(window.location.search).get('tab');
    if (t === 'players' || t === 'agents' || t === 'partners') setTab(t);
  }, []);
  const { data: s } = useApi<Summary>('/admin/liabilities/');
  const items: { id: Tab; label: string; count?: number }[] = [
    { id: 'players', label: `Players${s ? ` · ${money(s.players.total)}` : ''}`, count: s?.players.people },
    { id: 'agents', label: `Agents${s ? ` · ${money(s.agents.total)}` : ''}`, count: s?.agents.people },
    ...(s?.partners ? [{ id: 'partners' as Tab, label: `Partners · ${money(s.partners.total)}`, count: s.partners.people }] : []),
  ];
  return (
    <div className="space-y-6">
      <PageHeader icon={BsJournalText} eyebrow="Money" title="Money owed"
        description="Who the business owes right now, and how much each — from live balances."
        actions={s && <span className="text-sm">Total owed <b className="text-lg tabular-nums">{money(s.total)}</b></span>} />
      <Tabs value={tab} onChange={setTab} items={items} />
      {tab === 'players' ? <Players /> : tab === 'agents' ? <Agents /> : <Partners />}
    </div>
  );
}
