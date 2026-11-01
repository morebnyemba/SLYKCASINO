'use client';

import Link from 'next/link';
import { useEffect, useState } from 'react';
import { BsShieldExclamation } from 'react-icons/bs';
import {
  Badge, Btn, EmptyState, Field, Notice, PageHeader, Panel, Tabs, TextInput, cx, tableClass, tdClass, thClass, trClass,
} from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';
import type { RiskCase } from '@/lib/risk';

type State = 'open' | 'confirmed' | 'dismissed' | 'all';
interface CasesResponse { results: RiskCase[]; open: number; held_withdrawals: number }

/** Players the fraud engine stopped: held for review or suspended automatically. */
export default function RiskPage() {
  const [state, setState] = useState<State>('open');
  const { data, loading } = useApi<CasesResponse>(`/admin/risk/cases/?status=${state}`);
  const rows = data?.results ?? [];
  return (
    <div className="space-y-5">
      <PageHeader icon={BsShieldExclamation} eyebrow="Players" title="Fraud & risk"
        description="The fraud engine watches signups, deposits, bets, bonuses and withdrawals. Suspicious players are held for review (withdrawals held, no bonuses); serious cases are suspended automatically. Only a superuser closes a case." />
      {data && data.held_withdrawals > 0 && (
        <Notice tone="red">{data.held_withdrawals} withdrawal(s) are held by a fraud check — they can’t be paid until the player’s case is closed.</Notice>
      )}
      <Tabs value={state} onChange={setState} items={[
        { id: 'open', label: 'Open', count: data?.open, tone: 'red' },
        { id: 'confirmed', label: 'Confirmed fraud' }, { id: 'dismissed', label: 'Dismissed' }, { id: 'all', label: 'All' },
      ]} />
      <div className="overflow-hidden rounded-2xl border border-border/70 bg-card">
        {loading && !data ? <div className="h-40 animate-pulse bg-muted/40" /> : rows.length === 0 ? (
          <EmptyState icon={BsShieldExclamation} title={state === 'open' ? 'No open cases' : 'Nothing here'}>
            {state === 'open' ? 'Nobody is waiting for a fraud review.' : 'No cases with this outcome.'}
          </EmptyState>
        ) : (
          <div className="overflow-x-auto">
            <table className={tableClass}>
              <thead><tr>
                <th className={thClass}>Case</th><th className={thClass}>Player</th><th className={thClass}>Action</th>
                <th className={thClass}>Score</th><th className={thClass}>Reason</th><th className={thClass}>Opened</th>
              </tr></thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id} className={trClass}>
                    <td className={tdClass}><Link href={`/risk/${c.id}`} className="font-mono font-semibold text-secondary hover:underline">#{c.id}</Link></td>
                    <td className={tdClass}><Link href={`/players/${c.player_id}`} className="font-semibold hover:underline">{c.username ?? `#${c.player_id}`}</Link></td>
                    <td className={tdClass}>
                      <Badge tone={c.action === 'suspended' ? 'red' : 'gold'} dot>{c.action_label}</Badge>
                      {c.status !== 'open' && <p className="mt-1 text-xs text-muted-foreground">{c.status_label} by {c.decided_by}</p>}
                    </td>
                    <td className={cx(tdClass, 'font-bold tabular-nums')}>{c.score}</td>
                    <td className={cx(tdClass, 'max-w-[380px] text-xs')}>{c.reason}</td>
                    <td className={cx(tdClass, 'whitespace-nowrap text-xs text-muted-foreground')}>{new Date(c.created_at).toLocaleString()}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
      <RiskSettingsPanel />
    </div>
  );
}

type Settings = Record<string, string | number>;

const FIELDS: { key: string; label: string; hint: string }[] = [
  { key: 'review_score', label: 'Review at score', hint: 'Withdrawals held for review and bonuses stopped. Points: low 10, medium 25, high 50, critical 100.' },
  { key: 'suspend_score', label: 'Suspend at score', hint: 'Account suspended automatically. Any critical signal suspends on its own.' },
  { key: 'window_days', label: 'Signals count for (days)', hint: 'Older signals stop counting towards the score.' },
  { key: 'signup_ip_accounts', label: 'Accounts per IP before flagging', hint: 'Low signal only — mobile carriers share IPs.' },
  { key: 'big_bet_amount', label: 'Big first-day bet ($)', hint: 'A stake this size soon after signup.' },
  { key: 'new_account_hours', label: '…within (hours of signup)', hint: '' },
  { key: 'deposit_volume_24h', label: 'Deposits in 24h above ($)', hint: '' },
  { key: 'withdraw_after_bonus_hours', label: 'Withdrawal within (hours of a bonus)', hint: '' },
  { key: 'payout_numbers_7d', label: 'Different payout numbers in 7 days', hint: '' },
  { key: 'winnings_7d', label: 'Winnings credited in 7 days above ($)', hint: '' },
];

function RiskSettingsPanel() {
  const { accessToken, user } = useAuth();
  const { data, refetch } = useApi<Settings>('/admin/risk/settings/');
  const [form, setForm] = useState<Settings | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  useEffect(() => { if (data) setForm(data); }, [data]);
  const canEdit = !!user?.isSuperuser;

  async function save() {
    if (!accessToken || !form) return;
    setBusy(true);
    const res = await authedRequest('PUT', '/admin/risk/settings/', accessToken, form);
    setBusy(false);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: 'Thresholds saved.' });
    refetch();
  }

  return (
    <Panel title="Thresholds" description={canEdit ? 'When the engine flags, holds and suspends.' : 'Only a superuser can change these.'}>
      {notice && <div className="mb-4"><Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice></div>}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-5">
        {FIELDS.map((f) => (
          <Field key={f.key} label={f.label} hint={f.hint}>
            <TextInput inputMode="decimal" disabled={!canEdit} value={form?.[f.key] ?? ''}
              onChange={(e) => setForm((v) => v && { ...v, [f.key]: e.target.value.replace(/[^0-9.]/g, '') })} />
          </Field>
        ))}
      </div>
      {canEdit && <div className="mt-4 flex justify-end"><Btn variant="primary" busy={busy} onClick={save}>Save thresholds</Btn></div>}
    </Panel>
  );
}
