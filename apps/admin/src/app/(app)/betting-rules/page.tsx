'use client';

import Link from 'next/link';
import { BsBank, BsGift, BsSliders, BsTicket } from 'react-icons/bs';
import { PageHeader, Panel } from '@/components/console/ui';
import { BettingRulesPanel, WithdrawalLimitsPanel } from '@/components/settings/betting-rules';
import { LiveGuardPanel } from '@/components/sportsbook/live-guard';

const ELSEWHERE = [
  { href: '/promotions', icon: BsGift, label: 'Promotions', text: 'Welcome and deposit bonuses, and what they credit.' },
  { href: '/promo-codes', icon: BsTicket, label: 'Promo codes', text: 'Codes, their bonus amounts, limits and expiry.' },
  { href: '/withdrawals', icon: BsBank, label: 'Withdrawal queue', text: 'Requests waiting to be paid or rejected.' },
];

/** Every betting, wallet and withdrawal setting in one place. Saved values apply to the backend and the player site straight away. */
export default function BettingRulesPage() {
  return (
    <div className="space-y-6">
      <PageHeader icon={BsSliders} eyebrow="Settings" title="Betting rules"
        description="Stake limits, selections per ticket, minimum odds for each wallet, Bonus wallet rules, live-market protection and withdrawal limits. The backend enforces every rule, and the player site picks up changes within a minute." />
      <BettingRulesPanel />
      <LiveGuardPanel />
      <WithdrawalLimitsPanel />
      <Panel title="Also configured elsewhere">
        <div className="grid gap-3 sm:grid-cols-3">
          {ELSEWHERE.map(({ href, icon: Icon, label, text }) => (
            <Link key={href} href={href} className="flex gap-3 rounded-xl border border-border p-3 transition-colors hover:bg-muted/50">
              <Icon className="mt-0.5 shrink-0 text-secondary" size={16} />
              <span><span className="block text-sm font-semibold">{label}</span><span className="text-xs text-muted-foreground">{text}</span></span>
            </Link>
          ))}
        </div>
      </Panel>
    </div>
  );
}
