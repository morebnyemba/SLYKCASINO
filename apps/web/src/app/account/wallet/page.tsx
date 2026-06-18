'use client';

import { useState } from 'react';
import { FaDownload } from 'react-icons/fa';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { useApi, authedPost } from '@/lib/use-api';

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

  const [depositAmt, setDepositAmt] = useState('50');
  const [withdrawAmt, setWithdrawAmt] = useState('');
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);

  async function handleDeposit() {
    if (!accessToken) return;
    setBusy(true); setMsg('');
    const { error } = await authedPost(
      '/wallet/deposit/',
      { amount: depositAmt, currency: wallet?.currency ?? 'USD' },
      accessToken,
    );
    setMsg(error ? `Error: ${error}` : `Deposited ${depositAmt} ${wallet?.currency ?? 'USD'}.`);
    refetchWallet(); refetchLedger();
    setBusy(false);
  }

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
  const entries = Array.isArray(ledger) ? ledger : [];

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

      <Card>
        <CardContent className="pt-6">
          {wLoading ? (
            <p className="text-sm text-muted-foreground">Loading…</p>
          ) : (
            <p className="text-3xl font-bold">
              {balance} <span className="text-base font-normal text-muted-foreground">{currency}</span>
            </p>
          )}

          <div className="mt-5 grid gap-4 sm:grid-cols-2">
            <div className="space-y-2">
              <p className="text-sm font-medium">Deposit</p>
              <div className="flex gap-2">
                <input
                  type="number"
                  value={depositAmt}
                  onChange={(e) => setDepositAmt(e.target.value)}
                  min="1"
                  className="w-24 rounded-md border border-border bg-background px-3 py-1.5 text-sm"
                />
                <button
                  onClick={handleDeposit}
                  disabled={busy}
                  className="rounded-md bg-primary px-4 py-1.5 text-sm font-medium text-primary-foreground hover:opacity-90 disabled:opacity-50"
                >
                  Deposit
                </button>
              </div>
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
                  className="w-24 rounded-md border border-border bg-background px-3 py-1.5 text-sm"
                />
                <button
                  onClick={handleWithdraw}
                  disabled={busy || !withdrawAmt}
                  className="rounded-md border border-border bg-background px-4 py-1.5 text-sm font-medium hover:bg-accent disabled:opacity-50"
                >
                  Withdraw
                </button>
              </div>
            </div>
          </div>

          {msg && <p className="mt-3 text-sm text-muted-foreground">{msg}</p>}
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex-row items-center justify-between space-y-0">
          <CardTitle className="text-base">Transaction history</CardTitle>
          {entries.length > 0 && (
            <button
              onClick={exportCsv}
              className="flex items-center gap-1.5 rounded-md border border-border px-3 py-1.5 text-xs font-medium text-muted-foreground transition-colors hover:bg-accent"
            >
              <FaDownload size={11} />
              Export CSV
            </button>
          )}
        </CardHeader>
        <CardContent className="p-0">
          {lLoading ? (
            <p className="px-6 py-4 text-sm text-muted-foreground">Loading…</p>
          ) : entries.length === 0 ? (
            <p className="px-6 py-4 text-sm text-muted-foreground">No transactions yet.</p>
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
                    <td className={`px-4 py-2 font-mono ${parseFloat(e.amount) >= 0 ? 'text-green-600' : 'text-red-500'}`}>
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
    </div>
  );
}
