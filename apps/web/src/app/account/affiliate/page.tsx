'use client';

import { useState } from 'react';
import { FaHandshake } from 'react-icons/fa';
import { FaArrowRight, FaClockRotateLeft } from 'react-icons/fa6';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';
import { LoadingState, Spinner } from '@slyk/ui/components/spinner';
import { AffiliateAnalytics } from '@/components/affiliate/analytics';
import { PayoutDialog, type PayoutOptions } from '@/components/affiliate/payout-dialog';
import { ShareLink } from '@/components/affiliate/share-link';

interface Commission {
  id: number;
  kind: 'revshare' | 'cpa';
  period: string | null;
  base_amount: string;
  rate: string;
  amount: string;
  active_players: number;
  status: 'pending' | 'approved' | 'paid' | 'rejected';
  created_at: string;
}

interface Programme {
  welcome_bonus_percent: string;
  welcome_bonus_cap: string;
  welcome_bonus_wagering: string;
  welcome_bonus_min_deposit: string;
  cpa_min_turnover_multiple: string;
  negative_carryover: boolean;
}

interface Stats {
  carryover: string;
  clicks_30d: number;
  clicks_total: number;
  signups: number;
  depositors: number;
  active_this_month: number;
  ngr_this_month: string;
  estimated_commission: string;
  pending: string;
  paid: string;
  referrals: { player: string; joined: string; campaign: string; deposited: boolean; ngr_this_month: string }[];
}

interface Payout {
  id: number;
  amount: string;
  method: string;
  method_label: string;
  account_number: string;
  status: 'requested' | 'paid' | 'rejected';
  reference: string;
  note: string;
  created_at: string;
  decided_at: string | null;
}

interface Affiliate {
  code: string;
  status: 'pending' | 'active' | 'suspended' | 'rejected';
  revshare_percent: string;
  cpa_amount: string;
  cpa_min_deposit: string;
  cpa_percent: string;
  cpa_cap: string;
  programme?: Programme;
  stats?: Stats;
  balance?: { available: string; pending: string; in_payout: string; paid_out: string; carryover: string };
  payouts?: Payout[];
  payout_options?: PayoutOptions;
  commissions?: Commission[];
}

const money = (v: string | number) =>
  `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const pct = (v: string) => `${Number(v).toString()}%`;

function monthLabel(period: string | null) {
  if (!period) return '—';
  return new Date(`${period}T00:00:00`).toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
}

const STATUS_BADGE: Record<Commission['status'], 'default' | 'secondary' | 'destructive'> = {
  pending: 'secondary', approved: 'default', paid: 'default', rejected: 'destructive',
};
const STATUS_LABEL: Record<Commission['status'], string> = {
  pending: 'Awaiting approval', approved: 'In your balance', paid: 'Paid', rejected: 'Rejected',
};
const PAYOUT_BADGE: Record<Payout['status'], 'default' | 'secondary' | 'destructive'> = {
  requested: 'secondary', paid: 'default', rejected: 'destructive',
};
const PAYOUT_LABEL: Record<Payout['status'], string> = { requested: 'Being sent', paid: 'Paid', rejected: 'Declined' };

type TermsProps = Pick<Affiliate, 'revshare_percent' | 'cpa_amount' | 'cpa_min_deposit' | 'cpa_percent' | 'cpa_cap' | 'programme'>;

function Terms({ a }: { a: TermsProps }) {
  const p = a.programme;
  const turnover = p ? Number(p.cpa_min_turnover_multiple) : 0;
  return (
    <ul className="space-y-1.5 text-sm text-muted-foreground">
      <li><b className="text-foreground">{pct(a.revshare_percent)}</b> of the net gaming revenue of every player you refer, paid monthly.</li>
      {Number(a.cpa_percent) > 0 && (
        <li>
          <b className="text-foreground">{pct(a.cpa_percent)}</b> of each referred player’s first deposit
          {Number(a.cpa_cap) > 0 && <> (up to <b className="text-foreground">{money(a.cpa_cap)}</b> per player)</>}, paid once
          {turnover > 0 && <> they’ve bet {turnover === 1 ? 'the amount of' : `${turnover}×`} that deposit</>}.
        </li>
      )}
      {Number(a.cpa_amount) > 0 && (
        <li><b className="text-foreground">{money(a.cpa_amount)}</b> for each referral who deposits {money(a.cpa_min_deposit)} or more.</li>
      )}
      {p && Number(p.welcome_bonus_percent) > 0 && (
        <li>
          Your players get a <b className="text-foreground">{pct(p.welcome_bonus_percent)}</b> bonus on their first deposit
          {Number(p.welcome_bonus_cap) > 0 && <> (up to {money(p.welcome_bonus_cap)})</>} — a reason to use your link.
        </li>
      )}
      <li>
        Commission is paid into your wallet balance once approved. When your players win overall in a month you’re paid nothing for it —
        and nothing is ever taken from you.{' '}
        {p?.negative_carryover
          ? 'A losing month is carried forward and earned back from the following months before revenue share is paid again.'
          : 'Every month starts from zero.'}
      </li>
    </ul>
  );
}

function Apply({ onDone }: { onDone: () => void }) {
  const { accessToken } = useAuth();
  const { data: terms } = useApi<TermsProps>('/affiliates/terms/', { public: true });
  const [code, setCode] = useState('');
  const [website, setWebsite] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function submit() {
    if (!accessToken) return;
    setBusy(true); setError('');
    const res = await authedPost('/affiliates/me/', { code, website }, accessToken);
    setBusy(false);
    if (res.error) setError(res.error);
    else onDone();
  }

  return (
    <Card className="overflow-hidden rounded-2xl">
      <div className="bg-gradient-to-br from-primary via-primary to-secondary/80 px-6 py-7 text-white">
        <FaHandshake size={28} className="mb-3 text-gold" />
        <h2 className="text-xl font-extrabold">Refer players, earn every month</h2>
        <p className="mt-1 max-w-lg text-sm text-white/70">
          Share your link. When the players you bring sign up and play, you get a share of the revenue they generate — for as long as they play.
        </p>
      </div>
      <CardContent className="space-y-5 pt-6">
        {terms && <Terms a={terms} />}
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span className="font-medium">Preferred code <span className="text-muted-foreground">(optional)</span></span>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/[^A-Za-z0-9]/g, '').toUpperCase().slice(0, 24))}
              placeholder="e.g. TENDAI"
              className="w-full rounded-lg border border-border bg-input px-3 py-2 outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="font-medium">Where will you promote us? <span className="text-muted-foreground">(optional)</span></span>
            <input
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              placeholder="Website, channel or group"
              className="w-full rounded-lg border border-border bg-input px-3 py-2 outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
        </div>
        {error && <p className="text-sm font-semibold text-destructive">{error}</p>}
        <button
          onClick={submit}
          disabled={busy}
          className="rounded-lg bg-win px-5 py-2.5 text-sm font-extrabold text-win-foreground disabled:opacity-60"
        >
          {busy ? <span className="inline-flex items-center justify-center gap-2"><Spinner size={14} />Applying…</span> : 'Join the affiliate programme'}
        </button>
      </CardContent>
    </Card>
  );
}

function HeroStat({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl bg-white/10 px-3.5 py-3 backdrop-blur-sm">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-white/60">{label}</p>
      <p className="mt-0.5 text-lg font-extrabold tabular-nums">{value}</p>
      {hint && <p className="text-[11px] text-white/60">{hint}</p>}
    </div>
  );
}

type Tab = 'payouts' | 'commissions' | 'players' | 'terms';

function Dashboard({ a, refetch }: { a: Affiliate & { stats: Stats }; refetch: () => void }) {
  const s = a.stats;
  const b = a.balance ?? { available: '0', pending: '0', in_payout: '0', paid_out: '0', carryover: '0' };
  const [payOpen, setPayOpen] = useState(false);
  const [tab, setTab] = useState<Tab>('payouts');
  const p = a.programme;
  const welcome = p && Number(p.welcome_bonus_percent) > 0
    ? `${Number(p.welcome_bonus_percent)}%${Number(p.welcome_bonus_cap) > 0 ? ` (up to ${money(p.welcome_bonus_cap)})` : ''}` : undefined;
  const payouts = a.payouts ?? [];
  const commissions = a.commissions ?? [];

  return (
    <div className="space-y-6">
      <section className="overflow-hidden rounded-2xl bg-gradient-to-br from-primary via-primary to-secondary/80 p-5 text-white shadow-lg sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/60">Affiliate balance · code {a.code}</p>
            <p className="mt-1 text-4xl font-extrabold tabular-nums sm:text-5xl">{money(b.available)}</p>
            <p className="mt-1 text-sm text-white/70">Ready to withdraw — to your betting wallet instantly, or to mobile money or your bank.</p>
          </div>
          <button
            onClick={() => setPayOpen(true)}
            disabled={!(Number(b.available) > 0) || !a.payout_options}
            className="flex items-center gap-2 rounded-xl bg-win px-5 py-3 text-sm font-extrabold text-win-foreground shadow transition-transform hover:scale-[1.02] disabled:opacity-50 disabled:hover:scale-100"
          >
            Request payout <FaArrowRight size={12} />
          </button>
        </div>
        <div className="mt-5 grid grid-cols-2 gap-2.5 lg:grid-cols-4">
          <HeroStat label="Awaiting approval" value={money(b.pending)} hint="joins your balance once approved" />
          <HeroStat label="Being paid out" value={money(b.in_payout)} />
          <HeroStat label="Paid to you" value={money(b.paid_out)} hint="all time" />
          <HeroStat label="This month (est.)" value={money(s.estimated_commission)}
            hint={`${money(s.ngr_this_month)} revenue · ${s.active_this_month} active`} />
        </div>
        {Number(b.carryover) < 0 && (
          <p className="mt-3 rounded-lg bg-black/20 px-3 py-2 text-xs text-white/80">
            {money(-Number(b.carryover))} from earlier losing months is earned back before revenue share pays again.
          </p>
        )}
      </section>

      <Card className="rounded-2xl">
        <CardHeader className="pb-2"><CardTitle className="text-base">Share your link</CardTitle></CardHeader>
        <CardContent><ShareLink code={a.code} welcome={welcome} /></CardContent>
      </Card>

      <AffiliateAnalytics />

      <Card className="rounded-2xl">
        <CardHeader className="pb-0">
          <div className="-mx-1 flex gap-1 overflow-x-auto px-1" role="tablist">
            {([['payouts', `Payouts (${payouts.length})`], ['commissions', `Commissions (${commissions.length})`],
              ['players', `Referred players (${s.signups})`], ['terms', 'Your terms']] as [Tab, string][]).map(([id, label]) => (
              <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
                className={`shrink-0 border-b-2 px-3 py-2 text-sm font-bold transition-colors ${tab === id ? 'border-secondary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
                {label}
              </button>
            ))}
          </div>
        </CardHeader>
        <CardContent className="pt-4">
          {tab === 'payouts' && (payouts.length === 0 ? (
            <p className="flex items-center gap-2 py-4 text-sm text-muted-foreground"><FaClockRotateLeft /> No payouts yet — once a commission is approved you can withdraw it here.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-sm">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr><th className="py-2">Requested</th><th>To</th><th className="text-right">Amount</th><th className="text-right">Status</th></tr>
                </thead>
                <tbody>
                  {payouts.map((po) => (
                    <tr key={po.id} className="border-t border-border">
                      <td className="py-2.5 text-muted-foreground">{new Date(po.created_at).toLocaleDateString()}</td>
                      <td>
                        <span className="font-semibold">{po.method_label}</span>
                        {po.account_number && <span className="ml-1.5 font-mono text-xs text-muted-foreground">···{po.account_number.slice(-4)}</span>}
                        {(po.reference || po.note) && <span className="block text-xs text-muted-foreground">{po.status === 'paid' ? `Ref ${po.reference}` : po.note}</span>}
                      </td>
                      <td className="text-right font-bold tabular-nums">{money(po.amount)}</td>
                      <td className="text-right"><Badge variant={PAYOUT_BADGE[po.status]}>{PAYOUT_LABEL[po.status]}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}

          {tab === 'commissions' && (commissions.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">No commissions yet — deposit commissions appear once your players qualify; revenue share after each month closes.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-sm">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr><th className="py-2">For</th><th>Based on</th><th className="text-right">Amount</th><th className="text-right">Status</th></tr>
                </thead>
                <tbody>
                  {commissions.map((c) => (
                    <tr key={c.id} className="border-t border-border">
                      <td className="py-2.5">{c.kind === 'cpa' ? 'New depositor' : monthLabel(c.period)}</td>
                      <td className="text-muted-foreground">
                        {c.kind === 'cpa' ? `${money(c.base_amount)} first deposit × ${pct(c.rate)}` : `${money(c.base_amount)} revenue × ${pct(c.rate)}`}
                      </td>
                      <td className="text-right font-bold tabular-nums">{money(c.amount)}</td>
                      <td className="text-right"><Badge variant={STATUS_BADGE[c.status]}>{STATUS_LABEL[c.status]}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}

          {tab === 'players' && (s.referrals.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">Nobody has signed up through your link yet — share it above.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full min-w-[520px] text-sm">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr><th className="py-2">Player</th><th>Joined</th><th>Campaign</th><th>Deposited</th><th className="text-right">Revenue this month</th></tr>
                </thead>
                <tbody>
                  {s.referrals.map((r, i) => (
                    <tr key={i} className="border-t border-border">
                      <td className="py-2.5 font-semibold">{r.player}</td>
                      <td className="text-muted-foreground">{new Date(r.joined).toLocaleDateString()}</td>
                      <td className="text-muted-foreground">{r.campaign || '—'}</td>
                      <td>{r.deposited ? 'Yes' : 'No'}</td>
                      <td className="text-right tabular-nums">{money(r.ngr_this_month)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ))}

          {tab === 'terms' && <Terms a={a} />}
        </CardContent>
      </Card>

      {a.payout_options && (
        <PayoutDialog open={payOpen} onClose={() => setPayOpen(false)} available={b.available} options={a.payout_options} onDone={refetch} />
      )}
    </div>
  );
}

export default function AffiliatePage() {
  const { data, error, loading, refetch } = useApi<Affiliate>('/affiliates/me/');
  const notJoined = !!error && /404/.test(error);

  return (
    <div className="space-y-6">
      <h1 className="text-2xl font-bold">Affiliate dashboard</h1>
      {loading && !data ? (
        <LoadingState />
      ) : notJoined ? (
        <Apply onDone={refetch} />
      ) : error ? (
        <p className="text-sm text-destructive">Couldn’t load your affiliate account. <button onClick={refetch} className="underline">Retry</button></p>
      ) : data?.status === 'active' && data.stats ? (
        <Dashboard a={data as Affiliate & { stats: Stats }} refetch={refetch} />
      ) : data ? (
        <Card className="rounded-2xl">
          <CardContent className="space-y-2 pt-6">
            <p className="font-bold">
              {data.status === 'pending' ? 'Application received' : data.status === 'suspended' ? 'Affiliate account suspended' : 'Application not approved'}
            </p>
            <p className="text-sm text-muted-foreground">
              {data.status === 'pending'
                ? `We’re reviewing your application for code ${data.code}. Your link starts tracking as soon as it’s approved.`
                : 'Contact support if you think this is a mistake.'}
            </p>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
