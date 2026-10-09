'use client';

import { useState } from 'react';
import { BsCheck2Circle, BsXCircle } from 'react-icons/bs';
import {
  Badge, Btn, Drawer, EmptyState, Field, Notice, Tabs, TextInput, cx, money, tableClass, tdClass, thClass, trClass,
} from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';

interface Payout {
  id: number; affiliate_code: string; username: string; kyc_status: string; amount: string; method: string; method_label: string;
  account_name: string; account_number: string; bank_name: string; status: 'requested' | 'paid' | 'rejected';
  reference: string; note: string; created_at: string; decided_at: string | null;
}
type Page<T> = { results?: T[] } | T[];
const rows = <T,>(d?: Page<T> | null) => (Array.isArray(d) ? d : d?.results ?? []);
const TONE = { requested: 'gold', paid: 'green', rejected: 'red' } as const;

/** Affiliate payout requests: send the money, then mark it paid — or reject it. */
export function PayoutsTab() {
  const { accessToken } = useAuth();
  const [status, setStatus] = useState<'requested' | 'paid' | 'rejected' | ''>('requested');
  const { data, loading, refetch } = useApi<Page<Payout>>(`/admin/affiliate-payouts/?status=${status}`);
  const [acting, setActing] = useState<{ payout: Payout; verb: 'mark-paid' | 'reject' } | null>(null);
  const [reference, setReference] = useState('');
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  const list = rows(data);

  function open(payout: Payout, verb: 'mark-paid' | 'reject') {
    setActing({ payout, verb }); setReference(''); setNote('');
  }

  async function submit() {
    if (!accessToken || !acting) return;
    setBusy(true);
    const res = await authedPost(`/admin/affiliate-payouts/${acting.payout.id}/${acting.verb}/`, { reference, note }, accessToken);
    setBusy(false);
    setNotice(res.error ? { tone: 'red', text: res.error }
      : { tone: 'green', text: acting.verb === 'mark-paid' ? `Marked ${money(acting.payout.amount)} as sent to ${acting.payout.username}.` : 'Payout rejected — the amount is back in their balance.' });
    if (!res.error) setActing(null);
    refetch();
  }

  const destination = (p: Payout) => p.method === 'wallet' ? 'Betting wallet'
    : p.method === 'bank' ? `${p.bank_name} · ${p.account_name} · ${p.account_number}` : `${p.account_number}${p.account_name ? ` (${p.account_name})` : ''}`;

  return (
    <div className="space-y-4">
      <Tabs value={status} onChange={setStatus} items={[
        { id: 'requested', label: 'To send' }, { id: 'paid', label: 'Paid' }, { id: 'rejected', label: 'Rejected' }, { id: '', label: 'All' },
      ]} />
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}
      <div className="overflow-hidden rounded-2xl border border-border/70 bg-card">
        {loading && !data ? <div className="h-40 animate-pulse bg-muted/40" />
          : list.length === 0 ? (
            <EmptyState icon={BsCheck2Circle} title={status === 'requested' ? 'No payouts waiting' : 'Nothing here'}>
              {status === 'requested' ? 'Requests to mobile money or a bank appear here for you to send. Wallet payouts complete on their own.' : 'No payouts with this status.'}
            </EmptyState>
          ) : (
            <div className="overflow-x-auto">
              <table className={tableClass}>
                <thead><tr>
                  <th className={thClass}>Affiliate</th><th className={thClass}>Amount</th><th className={thClass}>Pay to</th>
                  <th className={thClass}>Requested</th><th className={thClass}>Status</th><th className={thClass} />
                </tr></thead>
                <tbody>
                  {list.map((p) => (
                    <tr key={p.id} className={trClass}>
                      <td className={tdClass}>
                        <p className="font-semibold">{p.username}</p>
                        <p className="text-xs text-muted-foreground">
                          <span className="font-mono">{p.affiliate_code}</span> · KYC{' '}
                          <span className={p.kyc_status === 'verified' ? 'text-win' : 'text-gold'}>{p.kyc_status || 'unknown'}</span>
                        </p>
                      </td>
                      <td className={cx(tdClass, 'text-base font-extrabold tabular-nums')}>{money(p.amount)}</td>
                      <td className={tdClass}>
                        <p className="font-semibold">{p.method_label}</p>
                        <p className="font-mono text-xs text-muted-foreground">{destination(p)}</p>
                      </td>
                      <td className={cx(tdClass, 'whitespace-nowrap text-xs text-muted-foreground')}>{new Date(p.created_at).toLocaleString()}</td>
                      <td className={tdClass}>
                        <Badge tone={TONE[p.status]} dot>{p.status}</Badge>
                        {(p.reference || p.note) && <p className="mt-1 max-w-[220px] truncate text-xs text-muted-foreground" title={p.note}>{p.reference || p.note}</p>}
                      </td>
                      <td className={cx(tdClass, 'text-right')}>
                        {p.status === 'requested' && (
                          <div className="flex justify-end gap-2">
                            <Btn size="sm" variant="success" icon={BsCheck2Circle} onClick={() => open(p, 'mark-paid')}>Mark sent</Btn>
                            <Btn size="sm" variant="danger" icon={BsXCircle} onClick={() => open(p, 'reject')}>Reject</Btn>
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
      </div>

      <Drawer open={!!acting} onClose={() => setActing(null)}
        title={acting?.verb === 'mark-paid' ? 'Mark payout as sent' : 'Reject payout'}
        description={acting ? `${money(acting.payout.amount)} to ${acting.payout.username} via ${acting.payout.method_label}` : ''}
        footer={<>
          <Btn onClick={() => setActing(null)}>Cancel</Btn>
          <Btn variant={acting?.verb === 'reject' ? 'danger' : 'success'} busy={busy} onClick={submit}
            disabled={acting?.verb === 'reject' && !note.trim()}>
            {acting?.verb === 'mark-paid' ? 'Confirm sent' : 'Reject payout'}
          </Btn>
        </>}>
        {acting && (
          <div className="space-y-4 text-sm">
            <div className="rounded-xl bg-muted/40 p-3">
              <p className="text-xs font-bold uppercase tracking-wide text-muted-foreground">Send to</p>
              <p className="mt-1 font-mono text-base font-semibold">{destination(acting.payout)}</p>
            </div>
            {acting.verb === 'mark-paid' ? (
              <>
                <p className="text-muted-foreground">Send the money first (e.g. from your EcoCash merchant account), then record it here. The affiliate is notified.</p>
                <Field label="Transaction reference" hint="e.g. the EcoCash/bank confirmation code — shown to the affiliate.">
                  <TextInput value={reference} onChange={(e) => setReference(e.target.value)} placeholder="MP241009.1530.A12345" />
                </Field>
                <Field label="Internal note (optional)"><TextInput value={note} onChange={(e) => setNote(e.target.value)} /></Field>
              </>
            ) : (
              <>
                <p className="text-muted-foreground">The amount goes back into the affiliate’s balance and they’re told why.</p>
                <Field label="Reason" hint="Shown to the affiliate."><TextInput value={note} onChange={(e) => setNote(e.target.value)} placeholder="The account name doesn’t match your verified name" /></Field>
              </>
            )}
          </div>
        )}
      </Drawer>
    </div>
  );
}
