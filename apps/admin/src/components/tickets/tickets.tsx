'use client';

import Link from 'next/link';
import { Fragment, useState } from 'react';
import { BsChevronDown, BsChevronRight } from 'react-icons/bs';
import { Badge, EmptyState, cx, money, tableClass, tdClass, thClass, trClass } from '@/components/console/ui';
import { useApi } from '@/lib/use-api';

interface Leg { id: number; event: string; match?: string | null; market_name?: string | null; outcome_label?: string | null; selection: string; odds: string; result: string }
export interface Ticket {
  ticket: string; kind: 'single' | 'multiple'; id: number; player_id: number | null; username: string;
  stake: string; odds?: string; combined_odds?: string; status: string; payout: string; placed_at: string;
  bonus?: string; cashout_paid?: string; stake_cashed_out?: string;
  event?: string; match?: string | null; market_name?: string | null; outcome_label?: string | null; selection?: string;
  legs?: Leg[];
}
export interface TicketsResponse {
  results: Ticket[];
  summary: { tickets: number; staked: string; returned: string; open: number } | null;
}

const TONE: Record<string, 'gold' | 'green' | 'red' | 'slate' | 'indigo'> = {
  open: 'gold', pending: 'gold', accepting: 'gold', won: 'green', lost: 'red', void: 'slate', cashed_out: 'indigo', rejected: 'red',
};

const pick = (x: { match?: string | null; event?: string; market_name?: string | null; outcome_label?: string | null; selection?: string }) => ({
  match: x.match || x.event || '—',
  pick: [x.market_name, x.outcome_label || x.selection].filter(Boolean).join(': '),
});

/** Tickets as players see them (#S12 single, #M5 multiple); click a multiple for its legs. */
export function TicketsTable({ tickets, showPlayer = true }: { tickets: Ticket[]; showPlayer?: boolean }) {
  const [open, setOpen] = useState<string | null>(null);
  if (tickets.length === 0) return <EmptyState title="No tickets">No tickets match.</EmptyState>;
  return (
    <div className="overflow-x-auto">
      <table className={tableClass}>
        <thead><tr>
          <th className={thClass}>Ticket</th>{showPlayer && <th className={thClass}>Player</th>}
          <th className={thClass}>Selection</th><th className={thClass}>Stake</th><th className={thClass}>Odds</th>
          <th className={thClass}>Return</th><th className={thClass}>Status</th><th className={thClass}>Placed</th>
        </tr></thead>
        <tbody>
          {tickets.map((t) => {
            const multi = t.kind === 'multiple';
            const isOpen = open === t.ticket;
            const one = pick(t);
            const returned = Number(t.payout) + Number(t.cashout_paid ?? 0);
            return (
              <Fragment key={t.ticket}>
                <tr className={cx(trClass, multi && 'cursor-pointer')} onClick={() => multi && setOpen(isOpen ? null : t.ticket)}>
                  <td className={cx(tdClass, 'whitespace-nowrap font-mono text-xs font-bold')}>
                    {multi && (isOpen ? <BsChevronDown className="mr-1 inline" /> : <BsChevronRight className="mr-1 inline" />)}#{t.ticket}
                  </td>
                  {showPlayer && (
                    <td className={tdClass}>
                      {t.player_id ? <Link href={`/players/${t.player_id}`} onClick={(e) => e.stopPropagation()} className="font-semibold hover:underline">{t.username}</Link> : '—'}
                    </td>
                  )}
                  <td className={cx(tdClass, 'max-w-[320px]')}>
                    {multi ? <span className="font-semibold">Multiple · {t.legs?.length ?? 0} legs</span> : (
                      <><p className="truncate font-semibold">{one.match}</p><p className="truncate text-xs text-muted-foreground">{one.pick}</p></>
                    )}
                  </td>
                  <td className={cx(tdClass, 'tabular-nums')}>{money(t.stake)}</td>
                  <td className={cx(tdClass, 'tabular-nums')}>{Number(t.odds ?? t.combined_odds ?? 0).toFixed(2)}</td>
                  <td className={cx(tdClass, 'font-semibold tabular-nums', returned > 0 && 'text-win')}>
                    {returned > 0 ? money(returned) : '—'}
                    {Number(t.cashout_paid ?? 0) > 0 && <p className="text-[11px] font-normal text-muted-foreground">cashed out {money(t.cashout_paid)}</p>}
                    {Number(t.bonus ?? 0) > 0 && <p className="text-[11px] font-normal text-muted-foreground">incl. bonus {money(t.bonus)}</p>}
                  </td>
                  <td className={tdClass}><Badge tone={TONE[t.status] ?? 'slate'} dot>{t.status.replace('_', ' ')}</Badge></td>
                  <td className={cx(tdClass, 'whitespace-nowrap text-xs text-muted-foreground')}>{new Date(t.placed_at).toLocaleString()}</td>
                </tr>
                {multi && isOpen && (t.legs ?? []).map((leg) => {
                  const l = pick(leg);
                  return (
                    <tr key={`${t.ticket}-${leg.id}`} className="bg-muted/30 text-sm">
                      <td className={tdClass} />{showPlayer && <td className={tdClass} />}
                      <td className={cx(tdClass, 'max-w-[320px]')}><p className="truncate font-medium">{l.match}</p><p className="truncate text-xs text-muted-foreground">{l.pick}</p></td>
                      <td className={tdClass} />
                      <td className={cx(tdClass, 'tabular-nums')}>{Number(leg.odds).toFixed(2)}</td>
                      <td className={tdClass} />
                      <td className={tdClass}><Badge tone={TONE[leg.result] ?? 'slate'}>{leg.result}</Badge></td>
                      <td className={tdClass} />
                    </tr>
                  );
                })}
              </Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

interface JetRow { id: number; round: number; stake: string; status: string; cashout_multiplier: string | null; payout: string; is_free?: boolean; created_at: string; crash_point: string | null }

/** A player's tickets, Aviator bets and withdrawals, for the player page. */
export function PlayerActivity({ playerId }: { playerId: number }) {
  const [tab, setTab] = useState<'tickets' | 'aviator' | 'withdrawals'>('tickets');
  const tickets = useApi<TicketsResponse>(tab === 'tickets' ? `/admin/tickets/?player_id=${playerId}` : null);
  const jet = useApi<{ results: JetRow[]; summary: { bets: number; staked: string; won: string; net: string } }>(tab === 'aviator' ? `/admin/jet/bets/?player_id=${playerId}` : null);
  const wd = useApi<{ results: { id: number; amount: string; method_label: string; account_number: string; status: string; status_label: string; reference: string; note: string; created_at: string }[] }>(
    tab === 'withdrawals' ? `/admin/withdrawals/?status=all&player_id=${playerId}` : null);
  const s = tickets.data?.summary;
  return (
    <div className="overflow-hidden rounded-2xl border border-border/70 bg-card">
      <div className="flex flex-wrap items-center gap-2 border-b border-border px-4 py-3">
        {([['tickets', 'Sportsbook tickets'], ['aviator', 'Aviator bets'], ['withdrawals', 'Withdrawals']] as const).map(([id, label]) => (
          <button key={id} onClick={() => setTab(id)}
            className={cx('rounded-lg px-3 py-1.5 text-sm font-semibold', tab === id ? 'bg-secondary text-secondary-foreground' : 'text-muted-foreground hover:bg-muted')}>
            {label}
          </button>
        ))}
        {tab === 'tickets' && s && (
          <p className="ml-auto text-xs text-muted-foreground">{s.tickets} tickets · {s.open} open · staked {money(s.staked)} · returned {money(s.returned)}</p>
        )}
        {tab === 'aviator' && jet.data && (
          <p className="ml-auto text-xs text-muted-foreground">{jet.data.summary.bets} bets · staked {money(jet.data.summary.staked)} · won {money(jet.data.summary.won)} · net {money(jet.data.summary.net)}</p>
        )}
      </div>
      {tab === 'tickets' && (tickets.loading && !tickets.data ? <div className="h-32 animate-pulse bg-muted/40" /> : <TicketsTable tickets={tickets.data?.results ?? []} showPlayer={false} />)}
      {tab === 'aviator' && (
        (jet.data?.results ?? []).length === 0 ? <EmptyState title="No Aviator bets">This player hasn’t played Aviator.</EmptyState> : (
          <div className="overflow-x-auto">
            <table className={tableClass}>
              <thead><tr><th className={thClass}>Round</th><th className={thClass}>Stake</th><th className={thClass}>Cashed at</th><th className={thClass}>Crash</th><th className={thClass}>Won</th><th className={thClass}>Status</th><th className={thClass}>Time</th></tr></thead>
              <tbody>
                {jet.data!.results.map((b) => (
                  <tr key={b.id} className={trClass}>
                    <td className={cx(tdClass, 'font-mono text-xs')}>#{b.round}</td>
                    <td className={cx(tdClass, 'tabular-nums')}>{money(b.stake)}{b.is_free && <Badge tone="gold">free</Badge>}</td>
                    <td className={cx(tdClass, 'tabular-nums')}>{b.cashout_multiplier ? `${Number(b.cashout_multiplier).toFixed(2)}x` : '—'}</td>
                    <td className={cx(tdClass, 'tabular-nums text-muted-foreground')}>{b.crash_point ? `${Number(b.crash_point).toFixed(2)}x` : '…'}</td>
                    <td className={cx(tdClass, 'font-semibold tabular-nums', Number(b.payout) > 0 && 'text-win')}>{Number(b.payout) > 0 ? money(b.payout) : '—'}</td>
                    <td className={tdClass}><Badge tone={TONE[b.status === 'cashed' ? 'won' : b.status] ?? 'slate'}>{b.status}</Badge></td>
                    <td className={cx(tdClass, 'whitespace-nowrap text-xs text-muted-foreground')}>{new Date(b.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
      {tab === 'withdrawals' && (
        (wd.data?.results ?? []).length === 0 ? <EmptyState title="No withdrawals">This player hasn’t asked to withdraw.</EmptyState> : (
          <div className="overflow-x-auto">
            <table className={tableClass}>
              <thead><tr><th className={thClass}>#</th><th className={thClass}>Amount</th><th className={thClass}>To</th><th className={thClass}>Status</th><th className={thClass}>Requested</th></tr></thead>
              <tbody>
                {wd.data!.results.map((w) => (
                  <tr key={w.id} className={trClass}>
                    <td className={cx(tdClass, 'font-mono text-xs')}>W{w.id}</td>
                    <td className={cx(tdClass, 'font-semibold tabular-nums')}>{money(w.amount)}</td>
                    <td className={tdClass}>{w.method_label} <span className="font-mono text-xs text-muted-foreground">{w.account_number}</span></td>
                    <td className={tdClass}>{w.status_label}{(w.reference || w.note) && <p className="text-xs text-muted-foreground">{w.reference || w.note}</p>}</td>
                    <td className={cx(tdClass, 'whitespace-nowrap text-xs text-muted-foreground')}>{new Date(w.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )
      )}
    </div>
  );
}
