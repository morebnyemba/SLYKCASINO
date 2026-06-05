import type { Metadata } from 'next';
import { Card, CardContent } from '@slyk/ui/components/card';
import { Button } from '@slyk/ui/components/button';
import { apiGet } from '@/lib/config';

export const metadata: Metadata = { title: 'Wallet — SLYK' };

interface Wallet {
  balance?: number;
  currency?: string;
}

export default async function WalletPage() {
  const wallet = (await apiGet<Wallet>('/wallet/')) as Wallet;
  const balance = typeof wallet.balance === 'number' ? wallet.balance : 0;
  return (
    <div>
      <h1 className="mb-4 text-2xl font-bold">Wallet</h1>
      <Card>
        <CardContent className="pt-6">
          <p className="text-3xl font-bold">
            {balance.toFixed(2)} <span className="text-base font-normal text-muted-foreground">{wallet.currency || 'USD'}</span>
          </p>
          <div className="mt-4 flex gap-3">
            <Button>Deposit</Button>
            <Button variant="secondary">Withdraw</Button>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
