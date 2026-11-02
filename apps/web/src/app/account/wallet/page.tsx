'use client';

import { useState } from 'react';
import { FaDownload, FaWallet } from 'react-icons/fa';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useApi } from '@/lib/use-api';
import { useWallets, WALLET_HINT, WALLET_IDS, WALLET_LABEL, type WalletsResponse } from '@/lib/wallets';
import { WithdrawPanel } from '@/components/withdraw-panel';
import { DepositBonuses } from '@/components/deposit-bonuses';
import { DepositModal } from '@/components/deposit-modal';
import { LoadingState, Spinner } from '@slyk/ui/components/spinner';

interface Wallet extends WalletsResponse {
  bonus_locked?: string;
  wagering_remaining?: string;
}

interface LedgerEntry {
  id: string | number;
  transaction_ref?: string;
  amount: string;
  kind: string;
  bucket?: 'deposit' | 'bonus' | 'winnings';
  reference: string;
  created_at: string;
}

const KIND_LABEL: Record<string, string> = {
  deposit: 'Deposit',
  withdrawal: 'Withdrawal (paid)',
  withdrawal_hold: 'Withdrawal on hold',
  withdrawal_fee: 'Withdrawal fee',
  deposit_refund: 'Deposit refund',
  migration: 'Wallet split',
  bonus_conversion: 'Bonus unlocked',
  bonus_forfeit: 'Bonus over the limit (forfeited)',
  bet_stake: 'Sports bet',
  bet_payout: 'Sports win',
  casino_debit: 'Aviator bet',
  casino_credit: 'Aviator win',
  bonus: 'Bonus',
  adjustment: 'Adjustment',
  affiliate: 'Affiliate commission',
};

function kindVariant(kind: string): 'default' | 'secondary' | 'destructive' | 'outline' {
  if (['deposit', 'bet_payout', 'casino_credit', 'bonus', 'affiliate'].includes(kind)) return 'default';
  // Only money leaving to the player is shown like a withdrawal; bets are neutral.
  if (['withdrawal', 'withdrawal_hold', 'withdrawal_fee', 'deposit_refund'].includes(kind)) return 'destructive';
  if (['bet_stake', 'casino_debit'].includes(kind)) return 'outline';
  return 'secondary';
}

export default function WalletPage() {
  const { data: wallet, loading: wLoading, refetch: refetchWallet } = useWallets<Wallet>();
  const { data: ledger, loading: lLoading, refetch: refetchLedger } = useApi<LedgerEntry[]>('/wallet/ledger/');

  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [depositOpen, setDepositOpen] = useState(false);
  const [depositAmount, setDepositAmount] = useState<number | undefined>();

  const balance = wallet?.balance ?? '0.00';
  const currency = wallet?.currency ?? 'USD';
  const allEntries = Array.isArray(ledger) ? ledger : [];
  const entries = allEntries.filter((e) => {
    const d = e.created_at.slice(0, 10);
    if (fromDate && d < fromDate) return false;
    if (toDate && d > toDate) return false;
    return true;
  });

  function exportCsv() {
    const header = 'Transaction,Type,Wallet,Amount,Reference,Date\n';
    const rows = entries.map((e) =>
      [e.transaction_ref ?? '', KIND_LABEL[e.kind] ?? e.kind, e.bucket ?? '', e.amount, e.reference || '', e.created_at].join(','),
    );
    const blob = new Blob([header + rows.join('\n')], { type: 'text/csv' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'wallet-transactions.csv';
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Wallet</h1>

      <Card className="overflow-hidden rounded-2xl border-gold/20">
        <div className="bg-gradient-to-br from-primary via-primary to-[#0B3BB8] px-6 py-6">
          <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-white/60">
            <FaWallet size={11} />
            Balance
          </p>
          {wLoading ? (
            <Spinner size={22} className="mt-2 text-white/80" label="Loading balance" />
          ) : (
            <p className="mt-1 text-3xl font-bold text-white">
              {balance} <span className="text-base font-normal text-white/60">{currency}</span>
            </p>
          )}
          {wallet?.wallets && (
            <div className="mt-4 grid gap-2 sm:grid-cols-3">
              {WALLET_IDS.map((id) => (
                <div key={id} className={`rounded-xl px-3 py-2.5 ${id === 'winnings' ? 'bg-white/20 ring-1 ring-gold/60' : 'bg-white/10'}`}>
                  <p className="text-[11px] font-bold uppercase tracking-wide text-white/70">{WALLET_LABEL[id]}</p>
                  <p className="text-xl font-extrabold tabular-nums text-white">{wallet.wallets[id].balance}</p>
                  <p className="mt-0.5 text-[11px] leading-snug text-white/70">
                    {WALLET_HINT[id]}
                    {id === 'deposit' && <> Bets need odds of {wallet.wallets[id].min_odds}+.</>}
                    {id === 'bonus' && wallet.bonus_rules && <>
                      {' '}Stake it all on one {wallet.bonus_rules.min_legs}+ selection multiple at {wallet.bonus_rules.min_leg_odds}+ each.
                      Win {wallet.bonus_rules.wins_needed} in a row to move up to ${Number(wallet.bonus_rules.max_conversion).toFixed(0)} to
                      Winnings — <b>{wallet.bonus_rules.wins} of {wallet.bonus_rules.wins_needed}</b> so far.
                    </>}
                  </p>
                </div>
              ))}
            </div>
          )}
        </div>
        <CardContent className="pt-6">
          <div className="grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <p className="text-sm font-medium">Deposit</p>
              <button
                onClick={() => setDepositOpen(true)}
                className="rounded-md bg-gradient-to-br from-gold to-gold/70 px-4 py-1.5 text-sm font-bold text-gold-foreground shadow transition-transform hover:scale-105"
              >
                Deposit funds
              </button>
            </div>

            <WithdrawPanel withdrawable={wallet?.withdrawable} onChanged={() => { refetchWallet(); refetchLedger(); }} />
          </div>

        </CardContent>
      </Card>

      <DepositBonuses onDeposit={(amount) => { setDepositAmount(amount); setDepositOpen(true); }} />

      <Card className="rounded-2xl border-gold/15">
        <CardHeader className="flex-col gap-3 space-y-0 sm:flex-row sm:items-center sm:justify-between">
          <CardTitle className="text-base">Transaction history</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <input
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-xs sm:flex-none"
            />
            <span className="text-xs text-muted-foreground">to</span>
            <input
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className="min-w-0 flex-1 rounded-md border border-border bg-background px-2 py-1.5 text-xs sm:flex-none"
            />
            {allEntries.length > 0 && (
              <button
                onClick={exportCsv}
                className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent/10"
              >
                <FaDownload size={11} />
                Export CSV
              </button>
            )}
          </div>
        </CardHeader>
        <CardContent className="p-0">
          {lLoading ? (
            <LoadingState className="py-6" />
          ) : entries.length === 0 ? (
            <p className="px-6 py-4 text-sm text-muted-foreground">
              {allEntries.length === 0 ? 'No transactions yet.' : 'No transactions in this date range.'}
            </p>
          ) : (
            <div className="overflow-x-auto">
            <table className="w-full min-w-[560px] text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="px-4 py-2">Type</th>
                  <th className="px-4 py-2">Wallet</th>
                  <th className="px-4 py-2">Amount</th>
                  <th className="px-4 py-2">Reference</th>
                  <th className="px-4 py-2">Date</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((e) => (
                  <tr key={e.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-2">
                      <Badge variant={kindVariant(e.kind)}>{KIND_LABEL[e.kind] ?? e.kind}</Badge>
                      {e.transaction_ref && <span className="mt-0.5 block font-mono text-[10px] text-muted-foreground">{e.transaction_ref}</span>}
                    </td>
                    <td className="px-4 py-2 text-muted-foreground">{e.bucket ? WALLET_LABEL[e.bucket] : '—'}</td>
                    <td className={`px-4 py-2 font-mono ${parseFloat(e.amount) >= 0 ? 'text-win' : 'text-down'}`}>
                      {parseFloat(e.amount) >= 0 ? '+' : ''}{e.amount}
                    </td>
                    <td className="px-4 py-2 text-muted-foreground">{e.reference || '—'}</td>
                    <td className="px-4 py-2 text-muted-foreground">
                      {new Date(e.created_at).toLocaleDateString()}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            </div>
          )}
        </CardContent>
      </Card>

      <DepositModal
        open={depositOpen}
        initialAmount={depositAmount}
        onClose={() => { setDepositOpen(false); setDepositAmount(undefined); refetchWallet(); refetchLedger(); }}
      />
    </div>
  );
}
