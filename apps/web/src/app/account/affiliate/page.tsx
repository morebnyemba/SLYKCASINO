'use client';

import { useState } from 'react';
import { FaHandshake } from 'react-icons/fa';
import { FaArrowRight, FaClockRotateLeft } from 'react-icons/fa6';
import { BsChevronDown, BsLink45Deg, BsPersonCheck, BsPersonPlus, BsPlayCircle } from 'react-icons/bs';
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
const pct = (v: string | number) => `${Number(v).toString()}%`;

function monthLabel(period: string | null) {
  if (!period) return '—';
  return new Date(`${period}T00:00:00`).toLocaleDateString(undefined, { month: 'long', year: 'numeric' });
}

const STATUS_BADGE: Record<Commission['status'], 'default' | 'secondary' | 'destructive'> = {
  pending: 'secondary', approved: 'default', paid: 'default', rejected: 'destructive',
};
const STATUS_LABEL: Record<Commission['status'], string> = {
  pending: 'Being checked', approved: 'In your balance', paid: 'Paid to you', rejected: 'Not approved',
};
const PAYOUT_BADGE: Record<Payout['status'], 'default' | 'secondary' | 'destructive'> = {
  requested: 'secondary', paid: 'default', rejected: 'destructive',
};
const PAYOUT_LABEL: Record<Payout['status'], string> = { requested: 'On its way', paid: 'Sent', rejected: 'Declined' };

type TermsProps = Pick<Affiliate, 'revshare_percent' | 'cpa_amount' | 'cpa_min_deposit' | 'cpa_percent' | 'cpa_cap' | 'programme'>;

/** The ways an affiliate earns, in plain words, with a worked example. */
function HowYouEarn({ a }: { a: TermsProps }) {
  const p = a.programme;
  const share = Number(a.revshare_percent);
  const turnover = p ? Number(p.cpa_min_turnover_multiple) : 0;
  const ways: React.ReactNode[] = [];
  if (share > 0) {
    ways.push(
      <>
        <b className="text-foreground">{pct(share)} of what your players lose</b>, every month, for as long as they play.
        <span className="block text-xs">Example: if your players lose {money(100)} between them in a month, you get {money(share)}.</span>
      </>,
    );
  }
  if (Number(a.cpa_amount) > 0) {
    ways.push(<><b className="text-foreground">{money(a.cpa_amount)} for every new player</b> who deposits {money(a.cpa_min_deposit)} or more. Paid once per player.</>);
  }
  if (Number(a.cpa_percent) > 0) {
    ways.push(
      <>
        <b className="text-foreground">{pct(a.cpa_percent)} of each new player’s first deposit</b>
        {Number(a.cpa_cap) > 0 && <> (up to {money(a.cpa_cap)} a player)</>}, paid once
        {turnover > 0 && <> they’ve bet {turnover === 1 ? 'that much' : `${turnover} times that much`}</>}.
        <span className="block text-xs">Example: a friend deposits {money(50)}, you get {money((50 * Number(a.cpa_percent)) / 100)}.</span>
      </>,
    );
  }
  return (
    <div className="space-y-4 text-sm text-muted-foreground">
      <ol className="space-y-3">
        {ways.map((w, i) => (
          <li key={i} className="flex gap-3">
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-win/15 text-xs font-extrabold text-win">{i + 1}</span>
            <span>{w}</span>
          </li>
        ))}
      </ol>
      {p && Number(p.welcome_bonus_percent) > 0 && (
        <p className="rounded-lg bg-gold/10 px-3 py-2 text-gold">
          Your friends get a <b>{pct(p.welcome_bonus_percent)} bonus</b> on their first deposit
          {Number(p.welcome_bonus_cap) > 0 && <> (up to {money(p.welcome_bonus_cap)})</>} when they join with your link. Tell them!
        </p>
      )}
      <p>
        <b className="text-foreground">You never lose money.</b> If your players win more than they lose in a month, you just earn nothing from that month.{' '}
        {p?.negative_carryover
          ? 'Their winnings are made up from the next months’ losses before your share starts again.'
          : 'Every month starts fresh.'}
      </p>
    </div>
  );
}

/** "What could I earn?": players × what each loses a month × the share. */
function Calculator({ share }: { share: number }) {
  const [players, setPlayers] = useState(10);
  const [loss, setLoss] = useState(20);
  const monthly = (players * loss * share) / 100;
  return (
    <div className="space-y-3 rounded-xl border border-border bg-muted/30 p-4 text-sm">
      <p className="font-bold">What could I earn?</p>
      <label className="block space-y-1">
        <span className="flex justify-between text-muted-foreground"><span>Friends playing</span><b className="text-foreground">{players}</b></span>
        <input type="range" min={1} max={200} value={players} onChange={(e) => setPlayers(Number(e.target.value))} className="w-full accent-[var(--secondary)]" />
      </label>
      <label className="block space-y-1">
        <span className="flex justify-between text-muted-foreground"><span>Each loses in a month (on average)</span><b className="text-foreground">{money(loss)}</b></span>
        <input type="range" min={5} max={200} step={5} value={loss} onChange={(e) => setLoss(Number(e.target.value))} className="w-full accent-[var(--secondary)]" />
      </label>
      <p className="rounded-lg bg-win/10 px-3 py-2 text-win">
        About <b className="text-lg">{money(monthly)}</b> a month for you · {money(monthly * 12)} a year
      </p>
      <p className="text-xs text-muted-foreground">A guide only: some months players win, some they lose more.</p>
    </div>
  );
}

const FAQ: [string, string][] = [
  ['When do I get paid?', 'Your share of a month is worked out after the month ends, checked, then added to your balance. New-player bonuses are added once the player qualifies. Withdraw your balance any time: to your betting wallet straight away, or to mobile money or your bank.'],
  ['Why is this month’s share $0?', 'Your share comes from what your players lose overall. If they’re winning this month, there’s nothing to share yet; it can change before the month ends.'],
  ['Can I ever owe money?', 'No. A month where your players win just earns nothing; nothing is ever taken from your balance.'],
  ['How do friends join through me?', 'They open your link before signing up, or type your code on the sign-up form. Either way they’re yours for good.'],
];

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
        <h2 className="text-xl font-extrabold">Invite friends, earn every month</h2>
        <p className="mt-1 max-w-lg text-sm text-white/75">
          Share your link. When friends join and play, you get a share of what they lose, every month, for as long as they play. It’s free and you can never lose money.
        </p>
        <ol className="mt-4 grid gap-2 text-sm sm:grid-cols-3">
          {['Share your link or code', 'Friends sign up and play', 'You get paid every month'].map((step, i) => (
            <li key={step} className="flex items-center gap-2 rounded-xl bg-white/10 px-3 py-2">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/20 text-xs font-extrabold">{i + 1}</span>{step}
            </li>
          ))}
        </ol>
      </div>
      <CardContent className="space-y-5 pt-6">
        {terms && (
          <>
            <HowYouEarn a={terms} />
            {Number(terms.revshare_percent) > 0 && <Calculator share={Number(terms.revshare_percent)} />}
          </>
        )}
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span className="font-medium">Your code <span className="text-muted-foreground">(optional, friends type it at sign-up)</span></span>
            <input
              value={code}
              onChange={(e) => setCode(e.target.value.replace(/[^A-Za-z0-9]/g, '').toUpperCase().slice(0, 24))}
              placeholder="e.g. TENDAI"
              className="w-full rounded-lg border border-border bg-input px-3 py-2 outline-none focus:ring-2 focus:ring-ring"
            />
          </label>
          <label className="space-y-1 text-sm">
            <span className="font-medium">Where will you share it? <span className="text-muted-foreground">(optional)</span></span>
            <input
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
              placeholder="WhatsApp groups, Facebook page…"
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
          {busy ? <span className="inline-flex items-center justify-center gap-2"><Spinner size={14} />Joining…</span> : 'Start earning'}
        </button>
      </CardContent>
    </Card>
  );
}

function MoneyChip({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-xl bg-white/10 px-3.5 py-3 backdrop-blur-sm">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-white/60">{label}</p>
      <p className="mt-0.5 text-lg font-extrabold tabular-nums">{value}</p>
      {hint && <p className="text-[11px] text-white/60">{hint}</p>}
    </div>
  );
}

/** Link clicks → signed up → deposited → playing this month. */
function Funnel({ s }: { s: Stats }) {
  const steps = [
    { icon: BsLink45Deg, n: s.clicks_total, label: 'opened your link' },
    { icon: BsPersonPlus, n: s.signups, label: 'signed up' },
    { icon: BsPersonCheck, n: s.depositors, label: 'deposited' },
    { icon: BsPlayCircle, n: s.active_this_month, label: 'playing this month' },
  ];
  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      {steps.map(({ icon: Icon, n, label }, i) => (
        <div key={label} className="relative rounded-xl border border-border bg-card p-3">
          <Icon className="mb-1.5 text-secondary" size={16} />
          <p className="text-xl font-extrabold tabular-nums">{n.toLocaleString()}</p>
          <p className="text-xs text-muted-foreground">{label}</p>
          {i < steps.length - 1 && <FaArrowRight className="absolute -right-2 top-1/2 z-10 hidden -translate-y-1/2 rounded-full bg-background text-muted-foreground sm:block" size={12} />}
        </div>
      ))}
    </div>
  );
}

type Tab = 'earnings' | 'players' | 'payouts';

function Dashboard({ a, refetch }: { a: Affiliate & { stats: Stats }; refetch: () => void }) {
  const s = a.stats;
  const b = a.balance ?? { available: '0', pending: '0', in_payout: '0', paid_out: '0', carryover: '0' };
  const [payOpen, setPayOpen] = useState(false);
  const [tab, setTab] = useState<Tab>('earnings');
  const p = a.programme;
  const welcome = p && Number(p.welcome_bonus_percent) > 0
    ? `${Number(p.welcome_bonus_percent)}%${Number(p.welcome_bonus_cap) > 0 ? ` (up to ${money(p.welcome_bonus_cap)})` : ''}` : undefined;
  const payouts = a.payouts ?? [];
  const commissions = a.commissions ?? [];
  const share = Number(a.revshare_percent);
  const lost = Number(s.ngr_this_month);

  return (
    <div className="space-y-6">
      {/* Your money */}
      <section className="overflow-hidden rounded-2xl bg-gradient-to-br from-primary via-primary to-secondary/80 p-5 text-white shadow-lg sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/60">Ready to withdraw · your code {a.code}</p>
            <p className="mt-1 text-4xl font-extrabold tabular-nums sm:text-5xl">{money(b.available)}</p>
            <p className="mt-1 text-sm text-white/70">Send it to your betting wallet straight away, or to mobile money or your bank.</p>
          </div>
          <button
            onClick={() => setPayOpen(true)}
            disabled={!(Number(b.available) > 0) || !a.payout_options}
            className="flex items-center gap-2 rounded-xl bg-win px-5 py-3 text-sm font-extrabold text-win-foreground shadow transition-transform hover:scale-[1.02] disabled:opacity-50 disabled:hover:scale-100"
          >
            Withdraw <FaArrowRight size={12} />
          </button>
        </div>
        <div className="mt-5 grid grid-cols-3 gap-2.5">
          <MoneyChip label="Being checked" value={money(b.pending)} hint="added to your balance soon" />
          <MoneyChip label="On its way to you" value={money(b.in_payout)} />
          <MoneyChip label="Paid to you so far" value={money(b.paid_out)} />
        </div>
      </section>

      {/* This month, in words */}
      <Card className="rounded-2xl">
        <CardContent className="space-y-1 pt-5">
          <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">This month so far</p>
          <p className="text-3xl font-extrabold tabular-nums text-win">{money(s.estimated_commission)}</p>
          <p className="text-sm text-muted-foreground">
            {s.active_this_month === 0
              ? 'None of your players has played yet this month. Share your link to get going.'
              : lost > 0
                ? <>Your {s.active_this_month} player{s.active_this_month === 1 ? '' : 's'} lost {money(lost)} between them this month. Your {pct(share)} share comes to {money(s.estimated_commission)}{Number(b.carryover) < 0 ? ' after earlier months are made up' : ''}, paid after the month ends.</>
                : <>Your {s.active_this_month} player{s.active_this_month === 1 ? '' : 's'} are up {money(-lost)} this month, so there’s no share yet. It can change before the month ends.</>}
          </p>
          {Number(b.carryover) < 0 && (
            <p className="pt-1 text-xs text-muted-foreground">
              Your players won {money(-Number(b.carryover))} more than they lost in earlier months. That’s made up first, then your share starts again.
            </p>
          )}
        </CardContent>
      </Card>

      <section className="space-y-2">
        <h2 className="text-sm font-bold">Your friends so far</h2>
        <Funnel s={s} />
      </section>

      <Card className="rounded-2xl">
        <CardHeader className="pb-2"><CardTitle className="text-base">Share your link</CardTitle></CardHeader>
        <CardContent><ShareLink code={a.code} welcome={welcome} /></CardContent>
      </Card>

      <Card className="rounded-2xl">
        <CardHeader className="pb-0">
          <div className="-mx-1 flex gap-1 overflow-x-auto px-1" role="tablist">
            {([['earnings', `Earnings (${commissions.length})`], ['players', `Your players (${s.signups})`],
              ['payouts', `Withdrawals (${payouts.length})`]] as [Tab, string][]).map(([id, label]) => (
              <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
                className={`shrink-0 border-b-2 px-3 py-2 text-sm font-bold transition-colors ${tab === id ? 'border-secondary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
                {label}
              </button>
            ))}
          </div>
        </CardHeader>
        <CardContent className="pt-4">
          {tab === 'earnings' && (commissions.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">Nothing yet. New-player bonuses show up once a friend qualifies; your monthly share after each month ends.</p>
          ) : (
            <ul className="divide-y divide-border">
              {commissions.map((c) => (
                <li key={c.id} className="flex items-start justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold">{c.kind === 'cpa' ? 'New player bonus' : `Your share for ${monthLabel(c.period)}`}</p>
                    <p className="text-xs text-muted-foreground">
                      {c.kind === 'cpa'
                        ? Number(c.rate) > 0 ? `${pct(c.rate)} of their ${money(c.base_amount)} first deposit` : 'A friend made their first deposit'
                        : `Your players lost ${money(c.base_amount)} · your ${pct(c.rate)}`}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="font-bold tabular-nums">{money(c.amount)}</p>
                    <Badge variant={STATUS_BADGE[c.status]}>{STATUS_LABEL[c.status]}</Badge>
                  </div>
                </li>
              ))}
            </ul>
          ))}

          {tab === 'players' && (s.referrals.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">Nobody has joined through your link yet. Share it above.</p>
          ) : (
            <ul className="divide-y divide-border">
              {s.referrals.map((r, i) => {
                const n = Number(r.ngr_this_month);
                return (
                  <li key={i} className="flex items-center justify-between gap-3 py-3">
                    <div className="min-w-0">
                      <p className="truncate text-sm font-semibold">{r.player}</p>
                      <p className="text-xs text-muted-foreground">
                        Joined {new Date(r.joined).toLocaleDateString()} · {r.deposited ? 'has deposited' : 'not deposited yet'}{r.campaign && ` · via ${r.campaign}`}
                      </p>
                    </div>
                    <p className="shrink-0 text-right text-xs text-muted-foreground">
                      This month<br />
                      <b className={`text-sm ${n > 0 ? 'text-foreground' : ''}`}>{n > 0 ? `lost ${money(n)}` : n < 0 ? `won ${money(-n)}` : '—'}</b>
                    </p>
                  </li>
                );
              })}
            </ul>
          ))}

          {tab === 'payouts' && (payouts.length === 0 ? (
            <p className="flex items-center gap-2 py-4 text-sm text-muted-foreground"><FaClockRotateLeft /> No withdrawals yet. Once money is in your balance, withdraw it above.</p>
          ) : (
            <ul className="divide-y divide-border">
              {payouts.map((po) => (
                <li key={po.id} className="flex items-start justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold">
                      To {po.method_label}{po.account_number && <span className="ml-1.5 font-mono text-xs text-muted-foreground">···{po.account_number.slice(-4)}</span>}
                    </p>
                    <p className="text-xs text-muted-foreground">
                      {new Date(po.created_at).toLocaleDateString()}{(po.reference || po.note) && ` · ${po.status === 'paid' ? `Ref ${po.reference}` : po.note}`}
                    </p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className="font-bold tabular-nums">{money(po.amount)}</p>
                    <Badge variant={PAYOUT_BADGE[po.status]}>{PAYOUT_LABEL[po.status]}</Badge>
                  </div>
                </li>
              ))}
            </ul>
          ))}
        </CardContent>
      </Card>

      <Card className="rounded-2xl">
        <CardHeader className="pb-2"><CardTitle className="text-base">How you earn</CardTitle></CardHeader>
        <CardContent className="space-y-4">
          <HowYouEarn a={a} />
          {share > 0 && <Calculator share={share} />}
        </CardContent>
      </Card>

      <Card className="rounded-2xl">
        <CardHeader className="pb-1"><CardTitle className="text-base">Questions</CardTitle></CardHeader>
        <CardContent className="divide-y divide-border">
          {FAQ.map(([q, ans]) => (
            <details key={q} className="group py-2.5">
              <summary className="flex cursor-pointer list-none items-center justify-between gap-2 text-sm font-semibold">
                {q}<BsChevronDown size={12} className="shrink-0 text-muted-foreground transition-transform group-open:rotate-180" />
              </summary>
              <p className="mt-1.5 text-sm text-muted-foreground">{ans}</p>
            </details>
          ))}
        </CardContent>
      </Card>

      {/* The full numbers, for affiliates who want them. */}
      <details className="group rounded-2xl border border-border bg-card">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-5 py-4 text-sm font-bold">
          Detailed stats and charts
          <BsChevronDown size={12} className="text-muted-foreground transition-transform group-open:rotate-180" />
        </summary>
        <div className="border-t border-border p-3 sm:p-4"><AffiliateAnalytics /></div>
      </details>

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
      <h1 className="text-2xl font-bold">Refer &amp; earn</h1>
      {loading && !data ? (
        <LoadingState />
      ) : notJoined ? (
        <Apply onDone={refetch} />
      ) : error ? (
        <p className="text-sm text-destructive">Couldn’t load your referral account. <button onClick={refetch} className="underline">Retry</button></p>
      ) : data?.status === 'active' && data.stats ? (
        <Dashboard a={data as Affiliate & { stats: Stats }} refetch={refetch} />
      ) : data ? (
        <Card className="rounded-2xl">
          <CardContent className="space-y-2 pt-6">
            <p className="font-bold">
              {data.status === 'pending' ? 'Thanks, we’re checking your request' : data.status === 'suspended' ? 'Your referral account is paused' : 'Request not approved'}
            </p>
            <p className="text-sm text-muted-foreground">
              {data.status === 'pending'
                ? `Your code ${data.code} starts working as soon as it’s approved. We’ll let you know.`
                : 'Contact support if you think this is a mistake.'}
            </p>
          </CardContent>
        </Card>
      ) : null}
    </div>
  );
}
