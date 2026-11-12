'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { BsBank, BsCheck2Circle, BsCopy, BsSearch, BsXCircle } from 'react-icons/bs';
import { PayoutsTab } from '@/components/affiliates/payouts-tab';
import { WithdrawalLimitsPanel } from '@/components/settings/betting-rules';
import {
  Badge, Btn, Drawer, EmptyState, Field, Notice, PageHeader, Pager, Panel, Tabs, TextInput, cx, money,
  tableClass, tdClass, thClass, trClass,
} from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';

interface Context {
  balance: string; deposits: string; paid_out: string; net: string; pending: string; bonus_locked: string;
  deposit_balance?: string; bonus_balance?: string; winnings_balance?: string;
  big_wins_7d: { amount: string; kind: string; created_at: string }[];
}
interface Withdrawal {
  id: number; player_id: number; username: string; kyc_status: string | null; amount: string;
  /** Withdrawal fee kept, and what the player is actually sent (amount − fee). */
  fee?: string; payout_amount?: string; method: string;
  /** Which wallet it is paid from: Winnings, or Deposit (at the deposit fee). */
  wallet?: 'winnings' | 'deposit';
  method_label: string; account_number: string; account_name: string; bank_name: string;
  status: 'requested' | 'paid' | 'rejected' | 'cancelled'; status_label: string; reference: string; note: string;
  created_at: string; decided_at: string | null; decided_by: string; context?: Context;
  legacy?: boolean; email?: string;
  /** Held by the fraud engine: can't be paid until the player's case is closed. */
  risk_hold?: boolean; risk_note?: string;
}
interface Queue { results: Withdrawal[]; count?: number; counts: { requested: number }; pending_total: string }
const WD_PAGE = 50;

const TONE = { requested: 'gold', paid: 'green', rejected: 'red', cancelled: 'slate' } as const;
type Status = Withdrawal['status'] | 'all';

/** Payouts aren't automatic: staff send each one, then record it here. */
export default function WithdrawalsPage() {
  const [tab, setTab] = useState<'players' | 'affiliates' | 'limits'>('players');
  return (
    <div className="space-y-6">
      <PageHeader icon={BsBank} eyebrow="Money" title="Withdrawals & payouts"
        description="Every request to be paid out. Send the money yourself (EcoCash, OneMoney, InnBucks or bank), then mark it paid with the transaction reference — or reject it and the money returns to the balance." />
      <Tabs value={tab} onChange={setTab} items={[
        { id: 'players', label: 'Player withdrawals' }, { id: 'affiliates', label: 'Affiliate payouts' }, { id: 'limits', label: 'Limits' },
      ]} />
      {tab === 'players' ? <PlayerWithdrawals /> : tab === 'affiliates' ? <PayoutsTab /> : (
        <div className="space-y-6">
          <WithdrawalLimitsPanel />
          <p className="text-sm text-muted-foreground">
            Stake limits, selections per ticket and each wallet&rsquo;s minimum odds are under{' '}
            <Link href="/betting-rules" className="font-semibold text-secondary hover:underline">Betting rules</Link>.
          </p>
        </div>
      )}
    </div>
  );
}

function destination(w: Withdrawal) {
  if (w.legacy) return `Not given — contact ${w.email || 'the player'}`;
  return w.method === 'bank' ? `${w.bank_name} · ${w.account_name} · ${w.account_number}`
    : `${w.account_number}${w.account_name ? ` (${w.account_name})` : ''}`;
}

function PlayerWithdrawals() {
  const { accessToken } = useAuth();
  const [status, setStatusRaw] = useState<Status>('requested');
  const [q, setQ] = useState('');
  const [search, setSearchRaw] = useState('');
  const [source, setSourceRaw] = useState<'' | 'winnings' | 'deposit'>('');
  const [page, setPage] = useState(1);
  const setStatus = (v: Status) => { setStatusRaw(v); setPage(1); };
  const setSearch = (v: string) => { setSearchRaw(v); setPage(1); };
  const setSource = (v: '' | 'winnings' | 'deposit') => { setSourceRaw(v); setPage(1); };
  const { data, loading, refetch } = useApi<Queue>(
    `/admin/withdrawals/?status=${status}&page=${page}&page_size=${WD_PAGE}${search ? `&q=${encodeURIComponent(search)}` : ''}${source ? `&wallet=${source}` : ''}`);
  const [acting, setActing] = useState<{ w: Withdrawal; verb: 'mark-paid' | 'reject' } | null>(null);
  const [text, setText] = useState('');
  // Paying is three steps: 1 check the player, 2 send the money, 3 confirm with the reference.
  const [step, setStep] = useState<1 | 2 | 3>(1);
  const [checked, setChecked] = useState(false);
  const [sent, setSent] = useState(false);
  const [confirmAmount, setConfirmAmount] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  const list = data?.results ?? [];

  useEffect(() => {
    const t = window.setInterval(refetch, 20000);
    return () => window.clearInterval(t);
  }, [refetch]);

  async function submit() {
    if (!accessToken || !acting) return;
    setBusy(true);
    const body = acting.verb === 'mark-paid' ? { reference: text, confirm_amount: confirmAmount } : { note: text };
    const res = await authedPost(`/admin/withdrawals/${acting.w.id}/${acting.verb}/`, body, accessToken);
    setBusy(false);
    setNotice(res.error ? { tone: 'red', text: res.error } : {
      tone: 'green',
      text: acting.verb === 'mark-paid' ? `Marked ${money(acting.w.amount)} to ${acting.w.username} as paid — they’ve been notified.`
        : `Rejected — ${money(acting.w.amount)} is back in ${acting.w.username}’s balance.`,
    });
    if (!res.error) setActing(null);
    refetch();
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Tabs value={status} onChange={setStatus} items={[
          { id: 'requested', label: 'To pay', count: status === 'requested' ? list.length : undefined },
          { id: 'paid', label: 'Paid' }, { id: 'rejected', label: 'Rejected' }, { id: 'cancelled', label: 'Cancelled' }, { id: 'all', label: 'All' },
        ]} />
        <select value={source} onChange={(e) => setSource(e.target.value as typeof source)} aria-label="Paid from"
          className="h-10 rounded-xl border border-border bg-background px-3 text-sm">
          <option value="">Winnings & deposit</option><option value="winnings">From Winnings</option><option value="deposit">From Deposit (high fee)</option>
        </select>
        <form onSubmit={(e) => { e.preventDefault(); setSearch(q.trim()); }} className="ml-auto flex items-center gap-2">
          <TextInput value={q} onChange={(e) => setQ(e.target.value)} placeholder="Player, number or reference" className="w-64" />
          <Btn type="submit" icon={BsSearch}>Search</Btn>
        </form>
      </div>
      {status === 'requested' && data && (
        <p className="text-sm text-muted-foreground">
          <b className="text-foreground">{data.counts.requested}</b> waiting · <b className="text-foreground">{money(data.pending_total)}</b> to send. Oldest first.
        </p>
      )}
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}

      <div className="overflow-hidden rounded-2xl border border-border/70 bg-card">
        {loading && !data ? <div className="h-40 animate-pulse bg-muted/40" />
          : list.length === 0 ? (
            <EmptyState icon={BsCheck2Circle} title={status === 'requested' ? 'No withdrawals waiting' : 'Nothing here'}>
              {status === 'requested' ? 'New requests appear here (and as a count in the menu).' : 'No withdrawals match.'}
            </EmptyState>
          ) : (
            <div className="overflow-x-auto">
              <table className={tableClass}>
                <thead><tr>
                  <th className={thClass}>#</th><th className={thClass}>Player</th><th className={thClass}>Amount</th>
                  <th className={thClass}>Pay to</th>
                  {status === 'requested' && <th className={thClass}>Check before paying</th>}
                  <th className={thClass}>Requested</th><th className={thClass}>Status</th><th className={thClass} />
                </tr></thead>
                <tbody>
                  {list.map((w) => (
                    <tr key={w.id} className={trClass}>
                      <td className={cx(tdClass, 'font-mono text-xs text-muted-foreground')}>W{w.id}</td>
                      <td className={tdClass}>
                        <Link href={`/players/${w.player_id}`} className="font-semibold hover:underline">{w.username}</Link>
                        <p className="text-xs text-muted-foreground">KYC <span className={w.kyc_status === 'verified' ? 'text-win' : 'text-gold'}>{w.kyc_status ?? '—'}</span></p>
                      </td>
                      <td className={cx(tdClass, 'text-base font-extrabold tabular-nums')}>
                        {money(w.amount)}
                        {w.wallet === 'deposit' && <p><Badge tone="gold">From Deposit</Badge></p>}
                        {Number(w.fee ?? 0) > 0 && <p className="text-xs font-semibold text-muted-foreground">send {money(w.payout_amount ?? w.amount)} · fee {money(w.fee!)}</p>}
                      </td>
                      <td className={tdClass}>
                        <p className="font-semibold">{w.legacy ? <Badge tone="gold">Earlier withdrawal</Badge> : w.method_label}</p>
                        <p className="font-mono text-xs text-muted-foreground">{destination(w)}</p>
                      </td>
                      {status === 'requested' && (
                        <td className={cx(tdClass, 'text-xs')}>
                          {w.context && <ContextCell c={w.context} />}
                        </td>
                      )}
                      <td className={cx(tdClass, 'whitespace-nowrap text-xs text-muted-foreground')}>{new Date(w.created_at).toLocaleString()}</td>
                      <td className={tdClass}>
                        <Badge tone={TONE[w.status]} dot>{w.status_label}</Badge>
                        {(w.reference || w.note) && <p className="mt-1 max-w-[220px] truncate text-xs text-muted-foreground" title={w.note || w.reference}>{w.reference || w.note}</p>}
                        {w.decided_by && <p className="text-[11px] text-muted-foreground">by {w.decided_by}</p>}
                      </td>
                      <td className={cx(tdClass, 'text-right')}>
                        {w.risk_hold && w.status === 'requested' && (
                          <p className="mb-1.5 text-right"><Link href="/risk"><Badge tone="red" dot>Held: fraud check</Badge></Link></p>
                        )}
                        {w.status === 'requested' && (
                          <div className="flex justify-end gap-2">
                            <Btn size="sm" variant="success" icon={BsCheck2Circle} disabled={w.risk_hold} title={w.risk_hold ? w.risk_note || 'Held by a fraud check' : undefined} onClick={() => { setActing({ w, verb: 'mark-paid' }); setText(''); setStep(1); setChecked(false); setSent(false); setConfirmAmount(''); }}>Mark paid</Btn>
                            <Btn size="sm" variant="danger" icon={BsXCircle} onClick={() => { setActing({ w, verb: 'reject' }); setText(''); }}>Reject</Btn>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <Pager page={page} count={data?.count ?? 0} pageSize={WD_PAGE} onPage={setPage} />
            </div>
          )}
      </div>

      <Drawer open={!!acting} onClose={() => setActing(null)}
        title={acting?.verb === 'mark-paid' ? `Pay withdrawal — step ${step} of 3` : 'Reject withdrawal'}
        description={acting ? `${money(acting.w.amount)} to ${acting.w.username} via ${acting.w.method_label}` : ''}
        footer={acting?.verb === 'reject' ? <>
          <Btn onClick={() => setActing(null)}>Cancel</Btn>
          <Btn variant="danger" busy={busy} onClick={submit} disabled={text.trim().length < 3}>Reject &amp; return money</Btn>
        </> : <>
          {step === 1 ? <Btn onClick={() => setActing(null)}>Cancel</Btn> : <Btn onClick={() => setStep((step - 1) as 1 | 2)}>Back</Btn>}
          {step === 1 && <Btn variant="primary" disabled={!checked} onClick={() => setStep(2)}>Next: send the money</Btn>}
          {step === 2 && <Btn variant="primary" disabled={!sent} onClick={() => setStep(3)}>Next: confirm</Btn>}
          {step === 3 && (
            <Btn variant="success" busy={busy} onClick={submit}
              disabled={text.trim().length < 3 || !acting || Number(confirmAmount) !== Number(sendAmount(acting.w))}>
              Confirm paid
            </Btn>
          )}
        </>}>
        {acting && acting.verb === 'mark-paid' && (
          <div className="space-y-4 text-sm">
            <ol className="flex gap-2 text-xs font-bold">
              {['Check', 'Send', 'Confirm'].map((label, i) => (
                <li key={label} className={cx('flex flex-1 items-center gap-2 rounded-lg px-2.5 py-1.5',
                  step === i + 1 ? 'bg-secondary text-secondary-foreground' : step > i + 1 ? 'bg-win/15 text-win' : 'bg-muted/50 text-muted-foreground')}>
                  <span className="flex h-5 w-5 items-center justify-center rounded-full bg-black/15">{step > i + 1 ? '✓' : i + 1}</span>{label}
                </li>
              ))}
            </ol>

            {step === 1 && (
              <>
                <p className="text-muted-foreground">Make sure this payout is legitimate before sending anything.</p>
                <div className="rounded-xl border border-border p-3">
                  <p><b>{acting.w.username}</b> · KYC <span className={acting.w.kyc_status === 'verified' ? 'text-win' : 'text-live'}>{acting.w.kyc_status ?? 'unknown'}</span></p>
                  <p className="text-muted-foreground">Requested {new Date(acting.w.created_at).toLocaleString()} · <Link href={`/players/${acting.w.player_id}`} className="text-secondary hover:underline">open player page</Link></p>
                </div>
                {acting.w.context && <ContextCell c={acting.w.context} wide />}
                {acting.w.legacy && (
                  <p className="rounded-xl bg-gold/10 p-3 text-gold">
                    Made with the old instant withdraw: the money already left the player’s balance, but they never said where to send it.
                    Contact them ({acting.w.email || 'no email'}) for their number first.
                  </p>
                )}
                <label className="flex items-start gap-2 rounded-xl bg-muted/40 p-3">
                  <input type="checkbox" className="mt-0.5 h-4 w-4" checked={checked} onChange={(e) => setChecked(e.target.checked)} />
                  <span>I’ve checked the player, their KYC and their activity, and this withdrawal should be paid.</span>
                </label>
              </>
            )}

            {step === 2 && (
              <>
                <p className="text-muted-foreground">Send the money now from your EcoCash / OneMoney / InnBucks merchant account or bank — exactly this amount, to exactly this account.</p>
                <div className="rounded-xl bg-muted/40 p-4">
                  <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Send exactly</p>
                  <p className="mt-1 flex items-center gap-2 text-3xl font-extrabold tabular-nums">
                    {money(sendAmount(acting.w))}
                    <button aria-label="Copy amount" title="Copy amount" onClick={() => navigator.clipboard?.writeText(sendAmount(acting.w))}
                      className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"><BsCopy size={14} /></button>
                  </p>
                  <p className="mt-3 text-xs font-bold uppercase tracking-wide text-muted-foreground">To ({acting.w.method_label})</p>
                  <p className="mt-1 flex items-center gap-2 font-mono text-base font-semibold">
                    {destination(acting.w)}
                    <button aria-label="Copy number" title="Copy number" onClick={() => navigator.clipboard?.writeText(acting.w.account_number)}
                      className="rounded p-1 text-muted-foreground hover:bg-muted hover:text-foreground"><BsCopy size={13} /></button>
                  </p>
                </div>
                <label className="flex items-start gap-2 rounded-xl bg-muted/40 p-3">
                  <input type="checkbox" className="mt-0.5 h-4 w-4" checked={sent} onChange={(e) => setSent(e.target.checked)} />
                  <span>I’ve sent exactly <b>{money(sendAmount(acting.w))}</b> to <b className="font-mono">{acting.w.account_number || 'the player'}</b> and the transfer went through.</span>
                </label>
              </>
            )}

            {step === 3 && (
              <>
                <p className="text-muted-foreground">Record the payment. The player is notified with the reference, and it counts as money paid out.</p>
                <Field label="Transaction reference" hint="The EcoCash/OneMoney/InnBucks or bank confirmation code.">
                  <TextInput value={text} onChange={(e) => setText(e.target.value)} placeholder="MP241011.1530.A12345" autoFocus />
                </Field>
                <Field label={`Type the amount you sent to confirm (${money(sendAmount(acting.w))})`}
                  hint={confirmAmount && Number(confirmAmount) !== Number(sendAmount(acting.w)) ? 'That doesn’t match the amount to send.' : 'Must match exactly.'}>
                  <TextInput inputMode="decimal" value={confirmAmount} onChange={(e) => setConfirmAmount(e.target.value.replace(/[^0-9.]/g, ''))} placeholder="0.00" />
                </Field>
              </>
            )}
          </div>
        )}
        {acting && acting.verb === 'reject' && (
          <div className="space-y-4 text-sm">
            <div className="rounded-xl bg-muted/40 p-3">
              <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Amount</p>
              <p className="mt-1 text-2xl font-extrabold tabular-nums">{money(acting.w.amount)}</p>
            </div>
            <p className="text-muted-foreground">The full amount (no fee) goes straight back to the player’s Winnings wallet and they’re told why.</p>
            <Field label="Reason" hint="Shown to the player.">
              <TextInput value={text} onChange={(e) => setText(e.target.value)} placeholder="The account name doesn’t match your verified name" />
            </Field>
          </div>
        )}
      </Drawer>
    </div>
  );
}

function ContextCell({ c, wide }: { c: Context; wide?: boolean }) {
  const net = Number(c.net);
  return (
    <div className={cx('space-y-0.5', wide && 'rounded-xl border border-border p-3')}>
      <p>Deposited <b>{money(c.deposits)}</b> · paid out <b>{money(c.paid_out)}</b></p>
      <p>Net in <b className={net < 0 ? 'text-live' : 'text-win'}>{money(c.net)}</b> · balance {money(c.balance)}</p>
      {c.winnings_balance != null && (
        <p className="text-muted-foreground">Deposit {money(c.deposit_balance!)} · Bonus {money(c.bonus_balance!)} · Winnings {money(c.winnings_balance)}</p>
      )}
      {Number(c.bonus_locked) > 0 && <p className="text-gold">Bonus locked {money(c.bonus_locked)}</p>}
      {c.big_wins_7d.length > 0 && (
        <p className="text-muted-foreground">Big wins (7d): {c.big_wins_7d.map((w) => money(w.amount)).join(', ')}</p>
      )}
    </div>
  );
}

/** What staff send: the request less its withdrawal fee. */
function sendAmount(w: Withdrawal) {
  return w.payout_amount ?? w.amount;
}
