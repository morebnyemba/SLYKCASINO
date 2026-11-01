'use client';

import Link from 'next/link';
import { Badge, Panel, cx, money, tableClass, tdClass, thClass, trClass } from '@/components/console/ui';
import { kindLabel, WALLET_LABEL, type WalletId } from '@/lib/ledger-kinds';
import { SEVERITY_TONE, type RiskReport } from '@/lib/risk';

/** Everything the fraud engine knows about a player: restrictions, every
 *  signal, linked accounts and why, numbers and IPs, wallets, withdrawals and
 *  recent transactions. Printable as it stands. */
export function RiskReportView({ report }: { report: RiskReport }) {
  const { profile, player } = report;
  return (
    <div className="space-y-5">
      <Panel title="Restrictions" description={`Score ${profile.score} (signals since the last review).`}>
        <div className="flex flex-wrap gap-2">
          {player.is_suspended && <Badge tone="red" dot>Suspended{player.suspended_reason ? ` — ${player.suspended_reason}` : ''}</Badge>}
          {profile.withdrawals_frozen && <Badge tone="red">Withdrawals frozen</Badge>}
          {profile.under_review && <Badge tone="gold">Under review — withdrawals held</Badge>}
          {profile.bonus_blocked && <Badge tone="gold">Bonuses blocked</Badge>}
          {!player.is_suspended && !profile.withdrawals_frozen && !profile.under_review && !profile.bonus_blocked && (
            <Badge tone="green">No restrictions</Badge>
          )}
        </div>
        <dl className="mt-4 grid grid-cols-3 gap-3 text-sm">
          {(['deposit', 'bonus', 'winnings'] as WalletId[]).map((w) => (
            <div key={w}><dt className="text-xs text-muted-foreground">{WALLET_LABEL[w]}</dt><dd className="font-semibold tabular-nums">{money(report.wallets[w])}</dd></div>
          ))}
        </dl>
      </Panel>

      <Panel title={`Signals (${report.signals.length})`} padded={false}>
        {report.signals.length === 0 ? <p className="p-4 text-sm text-muted-foreground">Nothing suspicious recorded.</p> : (
          <div className="overflow-x-auto">
            <table className={tableClass}>
              <thead><tr><th className={thClass}>When</th><th className={thClass}>Severity</th><th className={thClass}>Finding</th><th className={thClass}>Linked</th></tr></thead>
              <tbody>
                {report.signals.map((s) => (
                  <tr key={s.id} className={trClass}>
                    <td className={cx(tdClass, 'whitespace-nowrap text-xs text-muted-foreground')}>{new Date(s.created_at).toLocaleString()}</td>
                    <td className={tdClass}><Badge tone={SEVERITY_TONE[s.severity]}>{s.severity} · {s.points}</Badge></td>
                    <td className={tdClass}><p className="font-semibold">{s.detail}</p><p className="font-mono text-[11px] text-muted-foreground">{s.code}</p></td>
                    <td className={cx(tdClass, 'text-xs')}>
                      {s.linked_player_ids.map((id) => <Link key={id} href={`/players/${id}`} className="mr-1.5 text-secondary hover:underline">#{id}</Link>)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title={`Linked accounts (${report.linked_accounts.length})`}
        description="A shared deposit or payout number is a strong link. A shared IP alone is weak: mobile carriers put many customers on one IP.">
        {report.linked_accounts.length === 0 ? <p className="text-sm text-muted-foreground">No other account shares a number or IP.</p> : (
          <ul className="divide-y divide-border/60">
            {report.linked_accounts.map((l) => (
              <li key={l.player_id} className="flex flex-wrap items-center gap-2 py-2 text-sm">
                <Link href={`/players/${l.player_id}`} className="font-semibold hover:underline">{l.username ?? `#${l.player_id}`}</Link>
                {l.is_suspended && <Badge tone="red">Suspended</Badge>}
                {l.how.map((h) => <Badge key={h} tone={h === 'IP address' ? 'slate' : 'gold'}>{h}</Badge>)}
              </li>
            ))}
          </ul>
        )}
        <div className="mt-3 grid gap-2 text-xs text-muted-foreground sm:grid-cols-3">
          <p>Deposit numbers: {(report.numbers['deposit number'] ?? []).join(', ') || '—'}</p>
          <p>Payout numbers: {(report.numbers['payout number'] ?? []).join(', ') || '—'}</p>
          <p>IPs: {report.ips.join(', ') || '—'}</p>
        </div>
      </Panel>

      <Panel title="Withdrawals" padded={false}>
        {report.withdrawals.length === 0 ? <p className="p-4 text-sm text-muted-foreground">None.</p> : (
          <div className="overflow-x-auto">
            <table className={tableClass}>
              <thead><tr><th className={thClass}>When</th><th className={thClass}>Amount</th><th className={thClass}>To</th><th className={thClass}>Status</th></tr></thead>
              <tbody>
                {report.withdrawals.map((w) => (
                  <tr key={w.id} className={trClass}>
                    <td className={cx(tdClass, 'whitespace-nowrap text-xs text-muted-foreground')}>{new Date(w.created_at).toLocaleString()}</td>
                    <td className={cx(tdClass, 'font-semibold tabular-nums')}>{money(w.amount)}</td>
                    <td className={cx(tdClass, 'font-mono text-xs')}>{w.method_label} {w.account_number}</td>
                    <td className={tdClass}>{w.status_label}{w.risk_hold && <Badge tone="red" className="ml-1.5">Held</Badge>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>

      <Panel title="Recent transactions" padded={false}>
        <div className="overflow-x-auto">
          <table className={tableClass}>
            <thead><tr><th className={thClass}>Ref</th><th className={thClass}>Type</th><th className={thClass}>Wallet</th><th className={cx(thClass, 'text-right')}>Amount</th><th className={thClass}>When</th></tr></thead>
            <tbody>
              {report.transactions.map((t) => (
                <tr key={t.transaction_ref} className={trClass}>
                  <td className={cx(tdClass, 'font-mono text-xs text-muted-foreground')}>{t.transaction_ref}</td>
                  <td className={tdClass}>{kindLabel(t.kind)}</td>
                  <td className={cx(tdClass, 'text-xs')}>{WALLET_LABEL[t.wallet as WalletId] ?? t.wallet}</td>
                  <td className={cx(tdClass, 'text-right tabular-nums', Number(t.amount) < 0 ? '' : 'text-win')}>{t.amount}</td>
                  <td className={cx(tdClass, 'whitespace-nowrap text-xs text-muted-foreground')}>{new Date(t.created_at).toLocaleString()}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Panel>
    </div>
  );
}
