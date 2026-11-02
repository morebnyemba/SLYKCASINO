'use client';

import { GAME_WALLET_IDS, useWallets, WALLET_LABEL, type WalletId } from '@/lib/wallets';

/** "Pay from" for a game: the player picks Deposit or Winnings (bonus money is
 *  for sports bets only) and sees each balance. Nothing is charged until one is chosen. */
export function WalletSelect({ value, onChange, className = '' }: {
  value: WalletId | '';
  onChange: (w: WalletId) => void;
  className?: string;
}) {
  const { data } = useWallets();
  if (!data?.wallets) return null;
  return (
    <label className={`inline-flex items-center gap-2 text-sm ${className}`}>
      <span className="text-muted-foreground">Pay from</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value as WalletId)}
        className="rounded-md border border-border bg-background px-2 py-1 text-sm font-semibold"
      >
        <option value="" disabled>Choose a wallet</option>
        {GAME_WALLET_IDS.map((id) => (
          <option key={id} value={id}>{WALLET_LABEL[id]} · ${Number(data.wallets[id].balance).toFixed(2)}</option>
        ))}
      </select>
    </label>
  );
}
