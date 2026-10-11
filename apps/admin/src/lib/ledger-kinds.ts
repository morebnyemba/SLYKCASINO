// How each wallet movement is named and coloured in the console. Only
// \`withdrawal\` is money paid out to a player; stakes are bets, not withdrawals.
export const LEDGER_KINDS: Record<string, { label: string; tone: string }> = {
  deposit: { label: 'Deposit', tone: 'text-win' },
  withdrawal: { label: 'Withdrawal (paid out)', tone: 'text-gold' },
  withdrawal_hold: { label: 'Withdrawal hold', tone: 'text-muted-foreground' },
  bet_stake: { label: 'Sports bet', tone: 'text-sky-400' },
  bet_payout: { label: 'Sports win', tone: 'text-win' },
  casino_debit: { label: 'Aviator bet', tone: 'text-sky-400' },
  casino_credit: { label: 'Aviator win', tone: 'text-win' },
  bonus: { label: 'Bonus', tone: 'text-gold' },
  adjustment: { label: 'Manual adjustment', tone: 'text-muted-foreground' },
  affiliate: { label: 'Affiliate commission', tone: 'text-win' },
};

export const kindLabel = (kind: string) => LEDGER_KINDS[kind]?.label ?? kind;
export const kindTone = (kind: string) => LEDGER_KINDS[kind]?.tone ?? 'text-muted-foreground';

export const KIND_FILTERS: { id: string; label: string }[] = [
  { id: '', label: 'All types' },
  { id: 'deposit', label: 'Deposits' },
  { id: 'withdrawal', label: 'Withdrawals (paid out)' },
  { id: 'withdrawal_hold', label: 'Withdrawal holds' },
  { id: 'bet_stake,bet_payout', label: 'Sportsbook' },
  { id: 'casino_debit,casino_credit', label: 'Aviator' },
  { id: 'bonus', label: 'Bonuses' },
  { id: 'adjustment', label: 'Adjustments' },
  { id: 'affiliate', label: 'Affiliate' },
];
