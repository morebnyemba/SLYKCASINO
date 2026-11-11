'use client';

import { useEffect, useState } from 'react';
import { Btn, Field, Notice, Panel, TextInput } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';

type Tone = { tone: 'green' | 'red'; text: string } | null;
type FieldDef<T> = { key: keyof T; label: string; hint: string };

/** A settings form backed by one GET/PUT endpoint. Saved values apply to the next bet and the bet slip at once. */
function useSettings<T extends object>(path: string, saved: string) {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<T>(path);
  const [form, setForm] = useState<T | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<Tone>(null);
  useEffect(() => { if (data) setForm(data); }, [data]);

  async function save() {
    if (!accessToken || !form) return;
    setBusy(true);
    const res = await authedRequest('PUT', path, accessToken, form);
    setBusy(false);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: saved });
    refetch();
  }
  const set = (key: keyof T) => (e: React.ChangeEvent<HTMLInputElement>) =>
    setForm((v) => v && { ...v, [key]: e.target.value.replace(/[^0-9.]/g, '') });
  return { form, busy, notice, setNotice, save, set };
}

function Grid<T extends object>({ fields, form, set, cols = 'xl:grid-cols-3' }: {
  fields: FieldDef<T>[]; form: T | null; set: (key: keyof T) => (e: React.ChangeEvent<HTMLInputElement>) => void; cols?: string;
}) {
  return (
    <div className={`grid gap-4 sm:grid-cols-2 ${cols}`}>
      {fields.map((f) => (
        <Field key={String(f.key)} label={f.label} hint={f.hint}>
          <TextInput inputMode="decimal" value={String(form?.[f.key] ?? '')} onChange={set(f.key)} />
        </Field>
      ))}
    </div>
  );
}

interface BettingRules {
  min_stake: string; max_stake: string; max_selections: number | string;
  deposit_min_odds: string; bonus_min_odds: string; winnings_min_odds: string;
  bonus_min_legs: number | string; bonus_min_leg_odds: string; bonus_wins_to_convert: number | string; bonus_max_conversion: string;
  bonus_expiry_days: number | string;
}

/** Stake and selection limits, each wallet's minimum odds, and the Bonus wallet's rules. */
export function BettingRulesPanel() {
  const s = useSettings<BettingRules>('/admin/wallet-rules/', 'Betting rules saved — they apply to the next bet.');
  const ticket: FieldDef<BettingRules>[] = [
    { key: 'min_stake', label: 'Minimum stake per ticket ($)', hint: 'Every single, and a multiple’s one stake.' },
    { key: 'max_stake', label: 'Maximum stake per ticket ($)', hint: 'Bonus tickets stake the whole Bonus wallet, so stake limits don’t apply to them.' },
    { key: 'max_selections', label: 'Maximum selections per ticket', hint: 'Players can’t add more to the bet slip.' },
  ];
  const odds: FieldDef<BettingRules>[] = [
    { key: 'deposit_min_odds', label: 'Deposit wallet — minimum total odds', hint: 'A ticket paid from Deposit needs combined odds of at least this.' },
    { key: 'winnings_min_odds', label: 'Winnings wallet — minimum total odds', hint: '1.00 = any odds.' },
    { key: 'bonus_min_odds', label: 'Bonus wallet — minimum total odds', hint: 'Promotional money can be bet but never withdrawn.' },
  ];
  const bonus: FieldDef<BettingRules>[] = [
    { key: 'bonus_min_legs', label: 'Bonus ticket — minimum selections', hint: 'Bonus money is staked in full on one multiple of at least this many.' },
    { key: 'bonus_min_leg_odds', label: 'Bonus ticket — minimum odds per selection', hint: 'Every selection on a bonus ticket.' },
    { key: 'bonus_wins_to_convert', label: 'Bonus — wins in a row to unlock', hint: 'Winning bonus tickets pay back into Bonus; after this many in a row it moves to Winnings.' },
    { key: 'bonus_max_conversion', label: 'Bonus — most that unlocks ($)', hint: 'Anything above this is forfeited when the Bonus wallet unlocks.' },
    { key: 'bonus_expiry_days', label: 'Bonus — expires after (days unused)', hint: 'A Bonus wallet nobody bets from for this long is forfeited; players are warned 3 days before. An open bonus ticket keeps it. 0 = never.' },
  ];
  const heading = 'mb-3 mt-6 text-xs font-bold uppercase tracking-[0.14em] text-muted-foreground first:mt-0';
  return (
    <Panel title="Betting limits & wallet rules"
      description="Players choose which wallet pays for each ticket. The backend refuses any ticket that breaks these rules, and the bet slip shows them; changes apply to the next bet. A winning Deposit or Winnings ticket returns its stake to that wallet and pays the profit into Winnings. Bonus money is for sports only: the whole Bonus wallet on one multiple; winnings return to Bonus until enough wins in a row unlock it into Winnings, up to the limit.">
      {s.notice && <div className="mb-4"><Notice tone={s.notice.tone} onClose={() => s.setNotice(null)}>{s.notice.text}</Notice></div>}
      <p className={heading}>Every ticket</p>
      <Grid fields={ticket} form={s.form} set={s.set} />
      <p className={heading}>Minimum odds by wallet</p>
      <Grid fields={odds} form={s.form} set={s.set} />
      <p className={heading}>Bonus wallet</p>
      <Grid fields={bonus} form={s.form} set={s.set} cols="xl:grid-cols-4" />
      <div className="mt-4 flex justify-end"><Btn variant="primary" busy={s.busy} onClick={s.save}>Save betting rules</Btn></div>
    </Panel>
  );
}

interface WithdrawalLimits {
  min_amount: string; max_amount: string; daily_max: string; min_turnover_percent: number | string; fee_percent: string;
  deposit_fee_percent: string;
}

/** Withdrawal amounts and fees. */
export function WithdrawalLimitsPanel() {
  const s = useSettings<WithdrawalLimits>('/admin/withdrawal-settings/', 'Limits saved.');
  const fields: FieldDef<WithdrawalLimits>[] = [
    { key: 'min_amount', label: 'Minimum per withdrawal ($)', hint: 'Smallest amount a player can ask for.' },
    { key: 'max_amount', label: 'Maximum per withdrawal ($)', hint: 'Largest single request.' },
    { key: 'daily_max', label: 'Daily cap per player ($)', hint: 'Total a player may request per day (0 = no cap).' },
    { key: 'min_turnover_percent', label: 'Play-through of pre-split deposits (%)', hint: 'Only deposits made before the three-wallet split (now in Winnings). New deposits can never be withdrawn. 0 = off.' },
    { key: 'fee_percent', label: 'Winnings withdrawal fee (%)', hint: 'Kept from every withdrawal of winnings; the player is sent the rest.' },
    { key: 'deposit_fee_percent', label: 'Deposit withdrawal fee (%)', hint: 'Kept when a player chooses to withdraw from their Deposit wallet.' },
  ];
  return (
    <Panel title="Withdrawal limits" description="Players withdraw from Winnings, or from Deposit at the higher deposit fee — never from Bonus. Requests that break a rule are refused straight away with the reason, and never reach the queue: KYC not verified, not enough winnings, outside these limits, or pre-split deposits not yet played through. Attempts to withdraw Bonus money are refused and recorded in the audit log.">
      {s.notice && <div className="mb-4"><Notice tone={s.notice.tone} onClose={() => s.setNotice(null)}>{s.notice.text}</Notice></div>}
      <Grid fields={fields} form={s.form} set={s.set} />
      <div className="mt-4 flex justify-end"><Btn variant="primary" busy={s.busy} onClick={s.save}>Save limits</Btn></div>
    </Panel>
  );
}
