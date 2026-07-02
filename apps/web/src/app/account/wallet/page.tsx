'use client';

import { useState } from 'react';
import { FaDownload, FaWallet, FaArrowDown } from 'react-icons/fa';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { useApi, authedPost } from '@/lib/use-api';
import { DepositModal } from '@/components/deposit-modal';

interface Wallet {
  balance?: string;
  currency?: string;
}

interface LedgerEntry {
  id: string | number;
  amount: string;
  kind: string;
  reference: string;
  created_at: string;
}

const KIND_LABEL: Record<string, string> = {
  deposit: 'Deposit',
  withdrawal: 'Withdrawal',
  bet_stake: 'Bet stake',
  bet_payout: 'Bet payout',
  casino_debit: 'Casino bet',
  casino_credit: 'Casino win',
  bonus: 'Bonus',
  adjustment: 'Adjustment',
};

function kindVariant(kind: string): 'default' | 'secondary' | 'destructive' {
  if (['deposit', 'bet_payout', 'casino_credit', 'bonus'].includes(kind)) return 'default';
  if (['withdrawal', 'bet_stake', 'casino_debit'].includes(kind)) return 'destructive';
  return 'secondary';
}

export default function WalletPage() {
  const { accessToken } = useAuth();
  const { data: wallet, loading: wLoading, refetch: refetchWallet } = useApi<Wallet>('/wallet/');
  const { data: ledger, loading: lLoading, refetch: refetchLedger } = useApi<LedgerEntry[]>('/wallet/ledger/');

  const [withdrawAmt, setWithdrawAmt] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);
  const [fromDate, setFromDate] = useState('');
  const [toDate, setToDate] = useState('');
  const [depositOpen, setDepositOpen] = useState(false);

  async function handleWithdraw() {
    if (!accessToken || !withdrawAmt) return;
    setBusy(true); setMsg('');
    const { error } = await authedPost(
      '/wallet/withdraw/',
      { amount: withdrawAmt },
      accessToken,
    );
    setMsg(error ? `Error: ${error}` : `Withdrawal of ${withdrawAmt} submitted.`);
    refetchWallet(); refetchLedger();
    setBusy(false);
  }

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
    const header = 'Type,Amount,Reference,Date\n';
    const rows = entries.map((e) =>
      [KIND_LABEL[e.kind] ?? e.kind, e.amount, e.reference || '', e.created_at].join(','),
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
        <div className="bg-gradient-to-br from-primary via-primary to-secondary/80 px-6 py-6">
          <p className="flex items-center gap-1.5 text-xs font-medium uppercase tracking-wide text-white/60">
            <FaWallet size={11} />
            Balance
          </p>
          {wLoading ? (
            <p className="mt-1 text-sm text-white/70">Loading…</p>
          ) : (
            <p className="mt-1 text-3xl font-bold text-white">
              {balance} <span className="text-base font-normal text-white/60">{currency}</span>
            </p>
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

            <div className="space-y-2">
              <p className="text-sm font-medium">Withdraw</p>
              <div className="flex gap-2">
                <input
                  type="number"
                  value={withdrawAmt}
                  onChange={(e) => setWithdrawAmt(e.target.value)}
                  min="1"
                  placeholder="Amount"
                  className="w-24 rounded-md border border-border bg-background px-3 py-1.5 text-sm focus:outline-none focus:ring-2 focus:ring-secondary"
                />
                <button
                  onClick={handleWithdraw}
                  disabled={busy || !withdrawAmt}
                  className="flex items-center gap-1.5 rounded-md border border-border bg-background px-4 py-1.5 text-sm font-medium hover:bg-accent/10 disabled:opacity-50"
                >
                  <FaArrowDown size={11} />
                  Withdraw
                </button>
              </div>
            </div>
          </div>

          {msg && <p className="mt-3 text-sm text-muted-foreground">{msg}</p>}
        </CardContent>
      </Card>

      <Card className="rounded-2xl border-gold/15">
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">Transaction history</CardTitle>
          <div className="flex items-center gap-2">
            <input
              type="date"
              value={fromDate}
              onChange={(e) => setFromDate(e.target.value)}
              className="rounded-md border border-border bg-background px-2 py-1 text-xs"
            />
            <span className="text-xs text-muted-foreground">to</span>
            <input
              type="date"
              value={toDate}
              onChange={(e) => setToDate(e.target.value)}
              className="rounded-md border border-border bg-background px-2 py-1 text-xs"
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
            <p className="px-6 py-4 text-sm text-muted-foreground">Loading…</p>
          ) : entries.length === 0 ? (
            <p className="px-6 py-4 text-sm text-muted-foreground">
              {allEntries.length === 0 ? 'No transactions yet.' : 'No transactions in this date range.'}
            </p>
          ) : (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-xs text-muted-foreground">
                  <th className="px-4 py-2">Type</th>
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
                    </td>
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
          )}
        </CardContent>
      </Card>

      <DepositModal
        open={depositOpen}
        onClose={() => { setDepositOpen(false); refetchWallet(); refetchLedger(); }}
      />
    </div>
  );
}
