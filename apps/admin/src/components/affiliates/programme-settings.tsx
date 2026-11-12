'use client';

import { useEffect, useState } from 'react';
import { BsGift, BsPercent, BsArrowRepeat } from 'react-icons/bs';
import { Btn, Field, Notice, Panel, Switch, TextInput } from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';

interface Programme {
  welcome_bonus_percent: string; welcome_bonus_cap: string; welcome_bonus_wagering: string; welcome_bonus_min_deposit: string;
  default_revshare_percent: string; default_cpa_amount: string; default_cpa_min_deposit: string; default_cpa_percent: string;
  default_cpa_cap: string; cpa_min_turnover_multiple: string; negative_carryover: boolean; min_payout: string;
  external_payouts: boolean; auto_payout: boolean; auto_approve_commissions: boolean; updated_at: string;
  net_loss_since: string | null; net_loss_review_above: string;
}
type NumKey = Exclude<keyof Programme, 'negative_carryover' | 'external_payouts' | 'auto_payout' | 'auto_approve_commissions' | 'updated_at'
  | 'net_loss_since'>;

const n = (v: string) => Number(v).toLocaleString(undefined, { maximumFractionDigits: 2 });

/** Programme-wide referral settings: welcome bonus, new-affiliate terms, carry-over. */
export function ProgrammeSettings() {
  const { accessToken } = useAuth();
  const { data, refetch } = useApi<Programme>('/admin/affiliate-programme/');
  const [form, setForm] = useState<Programme | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  useEffect(() => { if (data) setForm(data); }, [data]);

  if (!form) return <div className="h-64 animate-pulse rounded-2xl bg-muted/50" />;
  const set = (k: NumKey) => (e: React.ChangeEvent<HTMLInputElement>) => setForm({ ...form, [k]: e.target.value.replace(/[^0-9.]/g, '') });
  const dirty = data && JSON.stringify(form) !== JSON.stringify(data);

  async function save() {
    if (!accessToken || !form) return;
    setBusy(true); setNotice(null);
    const { updated_at: _skip, net_loss_since: _since, ...body } = form;
    const res = await authedRequest('PUT', '/admin/affiliate-programme/', accessToken, body);
    setBusy(false);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: 'Saved — applies to new deposits and the next month closed.' });
    if (!res.error) refetch();
  }

  const num = (k: NumKey, label: string, hint: string) => (
    <Field label={label} hint={hint}><TextInput inputMode="decimal" value={form[k]} onChange={set(k)} /></Field>
  );
  const bonusExample = Math.min(50 * Number(form.welcome_bonus_percent) / 100, Number(form.welcome_bonus_cap) || Infinity);
  const cpaExample = Math.min(50 * Number(form.default_cpa_percent) / 100, Number(form.default_cpa_cap) || Infinity) + Number(form.default_cpa_amount || 0);

  return (
    <div className="space-y-6">
      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}
      <Panel title="Referred players’ welcome bonus" description="Credited automatically on a referred player’s first deposit, as bonus money that must be bet before it can be withdrawn."
        actions={<BsGift className="text-gold" />}>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {num('welcome_bonus_percent', 'Bonus (% of first deposit)', '0 turns the bonus off.')}
          {num('welcome_bonus_cap', 'Maximum bonus ($)', '0 = no maximum.')}
          {num('welcome_bonus_wagering', 'Wagering (× bonus)', 'Total to bet before the bonus can be withdrawn.')}
          {num('welcome_bonus_min_deposit', 'Minimum first deposit ($)', 'Smaller first deposits get no bonus.')}
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Example: a $50 first deposit gets a ${n(String(bonusExample))} bonus, withdrawable after ${n(String(bonusExample * Number(form.welcome_bonus_wagering)))} has been bet.
        </p>
      </Panel>

      <Panel title="New affiliates’ terms" description="What an affiliate starts on when they join. Change any affiliate’s own terms from the Affiliates tab."
        actions={<BsPercent className="text-secondary" />}>
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {num('default_revshare_percent', 'Commission on customers’ net loss (%)', 'Of what referred players lose (stakes − winnings), every game, closed daily.')}
          {num('default_cpa_percent', 'Deposit commission (% of first deposit)', 'Paid once per referred player.')}
          {num('default_cpa_cap', 'Deposit commission cap ($)', 'Per referred player. 0 = no cap.')}
          {num('default_cpa_amount', 'Flat CPA ($)', 'Added on top, once per referred player. 0 = off.')}
          {num('default_cpa_min_deposit', 'CPA minimum total deposits ($)', 'A referral must deposit at least this.')}
          {num('cpa_min_turnover_multiple', 'Play required (× first deposit)', 'They must also bet this many times their first deposit — stops deposit-and-withdraw farming.')}
        </div>
        <p className="mt-3 text-xs text-muted-foreground">
          Example: a referral’s $50 first deposit earns the affiliate ${n(String(cpaExample))} once they’ve bet ${n(String(50 * Number(form.cpa_min_turnover_multiple)))}. {form.auto_approve_commissions ? 'It is paid as soon as they qualify.' : 'It waits for your approval (see Payouts below).'}
        </p>
      </Panel>

      <Panel title="How agents earn" description="Agents earn their % of what their customers actually lose — real-money stakes minus winnings on sports, Aviator and casino, added up per agent and closed each night. Bonus-wallet play and free bets never count; bonus money turned into Winnings is deducted."
        actions={<BsPercent className="text-secondary" />}>
        <ul className="mb-4 list-disc space-y-1 pl-5 text-sm text-muted-foreground">
          <li>A day the customers win overall pays nothing and is earned back from the next days first (carried forward).</li>
          <li>Betting both sides with two customers nets out inside the agent’s total; an agent’s own account, and any account sharing a deposit or payout number with the agent or a customer, can only reduce it (their winnings count, their losses don’t).</li>
          <li>A stake counts on the day its bet settles, so bets left open at midnight can’t be cashed in.</li>
          {form.net_loss_since && <li>In force since {new Date(form.net_loss_since).toLocaleString()}; losing tickets settled before were paid one by one.</li>}
        </ul>
        <div className="grid gap-4 sm:grid-cols-2">
          {num('net_loss_review_above', 'Review a day’s commission above ($)', 'Bigger days wait for your approval under Commissions before they are paid. 0 = never.')}
        </div>
      </Panel>

      <Panel title="Losing months" description="When an affiliate’s players win overall in a month, no commission is paid — and nothing is ever taken from the affiliate."
        actions={<BsArrowRepeat className="text-muted-foreground" />}>
        <div className="flex items-start justify-between gap-6">
          <div className="text-sm">
            <p className="font-semibold">Carry losing months forward</p>
            <p className="mt-1 text-muted-foreground">
              On: a −$500 month must be earned back before revenue share is paid again (industry standard).
              Off: every month starts from zero.
            </p>
          </div>
          <Switch checked={form.negative_carryover} onChange={(v) => setForm({ ...form, negative_carryover: v })} label="Carry losing months forward" />
        </div>
      </Panel>

      <Panel title="Payouts" description="When affiliates get their money. With automatic payout on, every commission goes into the affiliate’s Winnings wallet the moment it is final, and they withdraw it like any winnings (KYC, fraud checks and the withdrawal fee apply as usual).">
        <div className="mb-6 grid gap-6 sm:grid-cols-2">
          <div className="flex items-start justify-between gap-4">
            <div className="text-sm">
              <p className="font-semibold">Pay earnings into the Winnings wallet automatically</p>
              <p className="mt-1 text-muted-foreground">
                Losing-ticket commission 3 minutes after the ticket settles; a deposit commission as soon as it qualifies.
                Suspended affiliates aren’t paid until reactivated. Off: earnings build up in the affiliate balance until they request a payout.
              </p>
            </div>
            <Switch checked={form.auto_payout} onChange={(v) => setForm({ ...form, auto_payout: v })} label="Pay earnings into the Winnings wallet automatically" />
          </div>
          <div className="flex items-start justify-between gap-4">
            <div className="text-sm">
              <p className="font-semibold">Deposit commissions need no approval</p>
              <p className="mt-1 text-muted-foreground">
                On: a deposit (CPA) commission is final when the referral qualifies. Off: you approve each one under Commissions first, then it is paid.
              </p>
            </div>
            <Switch checked={form.auto_approve_commissions} onChange={(v) => setForm({ ...form, auto_approve_commissions: v })} label="Deposit commissions need no approval" />
          </div>
        </div>
        <div className="grid gap-6 sm:grid-cols-2">
          {num('min_payout', 'Minimum payout to mobile money / bank ($)', 'Moving earnings into the betting wallet has no minimum.')}
          <div className="flex items-start justify-between gap-4">
            <div className="text-sm">
              <p className="font-semibold">Offer mobile money and bank payouts</p>
              <p className="mt-1 text-muted-foreground">Off: affiliates can only move earnings into their betting wallet (then withdraw as players, with KYC).</p>
            </div>
            <Switch checked={form.external_payouts} onChange={(v) => setForm({ ...form, external_payouts: v })} label="Offer mobile money and bank payouts" />
          </div>
        </div>
      </Panel>

      <div className="flex justify-end">
        <Btn variant="primary" busy={busy} disabled={!dirty} onClick={save}>Save programme settings</Btn>
      </div>
    </div>
  );
}
