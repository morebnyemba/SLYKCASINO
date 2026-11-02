'use client';

import { useEffect } from 'react';
import { useAuth } from '@/lib/auth-context';
import { useApi } from '@/lib/use-api';

/** The three balances every player has. Only Winnings can be withdrawn. */
export type WalletId = 'deposit' | 'bonus' | 'winnings';

export const WALLET_IDS: WalletId[] = ['deposit', 'bonus', 'winnings'];

export const WALLET_LABEL: Record<WalletId, string> = {
  deposit: 'Deposit',
  bonus: 'Bonus',
  winnings: 'Winnings',
};

export const WALLET_HINT: Record<WalletId, string> = {
  deposit: 'Money you deposited. Bet it — it can’t be withdrawn.',
  bonus: 'Promotional money for sports bets. Win it into Winnings — it can’t be withdrawn as it is.',
  winnings: 'What you’ve won. The only balance you can withdraw.',
};

export interface WalletInfo { balance: string; min_odds: string; withdrawable: boolean }

/** The Bonus wallet's rules and the player's progress towards unlocking it. */
export interface BonusRules {
  wins: number; wins_needed: number; max_conversion: string; min_legs: number; min_leg_odds: string;
}

export interface WalletsResponse {
  balance: string;
  currency: string;
  wallets: Record<WalletId, WalletInfo>;
  withdrawable: string;
  withdrawal_fee_percent: string;
  bonus_rules?: BonusRules;
}

/** Wallets a game (Aviator, casino) can be played from: never Bonus. */
export const GAME_WALLET_IDS: WalletId[] = ['deposit', 'winnings'];

/** Whether a slip may be paid from the Bonus wallet (the server checks the same). */
export function bonusEligible(rules: BonusRules | undefined, legOdds: number[], isMultiple: boolean): string | null {
  if (!rules) return null;
  if (!isMultiple || legOdds.length < rules.min_legs) return `Bonus bets need one multiple of ${rules.min_legs}+ selections`;
  if (legOdds.some((o) => o + 1e-9 < Number(rules.min_leg_odds))) return `Every selection needs odds of ${rules.min_leg_odds}+`;
  return null;
}

/** Fired after anything that moves money (a bet, a cash-out) so balances refresh. */
export const WALLET_CHANGED = 'slyk:wallet-changed';

export function announceWalletChange() {
  window.dispatchEvent(new Event(WALLET_CHANGED));
}

/** The signed-in player's three balances, kept fresh as money moves. */
export function useWallets<T extends WalletsResponse = WalletsResponse>() {
  const { user } = useAuth();
  const api = useApi<T>(user ? '/wallet/' : null);
  const { refetch } = api;
  useEffect(() => {
    const onChange = () => refetch();
    window.addEventListener(WALLET_CHANGED, onChange);
    return () => window.removeEventListener(WALLET_CHANGED, onChange);
  }, [refetch]);
  return api;
}

/** Would a ticket at these odds be accepted from this wallet? */
export function meetsMinOdds(info: WalletInfo | undefined, odds: number) {
  return !!info && odds + 1e-9 >= Number(info.min_odds);
}
