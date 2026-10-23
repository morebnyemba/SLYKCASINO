'use client';

import Link from 'next/link';
import { useMemo, useState } from 'react';
import { FaHandshake } from 'react-icons/fa';
import { FaArrowRight, FaClockRotateLeft } from 'react-icons/fa6';
import { BsCheckCircleFill, BsLink45Deg, BsPersonPlus, BsTicketPerforated, BsXCircleFill } from 'react-icons/bs';
import { Card, CardContent, CardHeader } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';
import { LoadingState, Spinner } from '@slyk/ui/components/spinner';
import { PayoutDialog, type PayoutOptions } from '@/components/affiliate/payout-dialog';
import { ShareLink } from '@/components/affiliate/share-link';

interface Commission {
  id: number;
  kind: 'stake' | 'revshare' | 'cpa';
  period: string | null;
  base_amount: string;
  rate: string;
  amount: string;
  active_players: number;
  status: 'pending' | 'approved' | 'paid' | 'rejected';
  note: string;
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
  commission_rate: string;
  lost_stakes_today: string;
  losing_tickets_today: number;
  commission_today: string;
  commission_month: string;
  commission_total: string;
  tickets_today: { played: number; won: number; lost: number; open: number };
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

function dayLabel(period: string | null) {
  if (!period) return '—';
  return new Date(`${period}T00:00:00`).toLocaleDateString(undefined, { weekday: 'short', day: 'numeric', month: 'short' });
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

/** The ways an agent earns, in plain words, with a worked example. */
function HowYouEarn({ a }: { a: TermsProps }) {
  const p = a.programme;
  const share = Number(a.revshare_percent);
  const turnover = p ? Number(p.cpa_min_turnover_multiple) : 0;
  const ways: React.ReactNode[] = [];
  if (share > 0) {
    ways.push(
      <>
        <b className="text-foreground">{pct(share)} of the stake on every ticket your customers lose</b>, for as long as they play.
        <span className="block text-xs">Example: a customer stakes {money(10)} and the ticket loses, you get {money(share / 10)}.</span>
      </>,
    );
  }
  if (Number(a.cpa_amount) > 0) {
    ways.push(<><b className="text-foreground">{money(a.cpa_amount)} for every new customer</b> who deposits {money(a.cpa_min_deposit)} or more. Paid once per customer.</>);
  }
  if (Number(a.cpa_percent) > 0) {
    ways.push(
      <>
        <b className="text-foreground">{pct(a.cpa_percent)} of each new customer’s first deposit</b>
        {Number(a.cpa_cap) > 0 && <> (up to {money(a.cpa_cap)} a customer)</>}, paid once
        {turnover > 0 && <> they’ve bet {turnover === 1 ? 'that much' : `${turnover} times that much`}</>}.
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
          Your customers get a <b>{pct(p.welcome_bonus_percent)} bonus</b> on their first deposit
          {Number(p.welcome_bonus_cap) > 0 && <> (up to {money(p.welcome_bonus_cap)})</>} when they join with your link. Tell them!
        </p>
      )}
      <p>Your commission is added every day. <b className="text-foreground">Withdraw from {money(MIN_WITHDRAWAL)}, any day.</b></p>
    </div>
  );
}

const MIN_WITHDRAWAL = 10;

function Apply({ onDone }: { onDone: () => void }) {
  const { accessToken } = useAuth();
  const { data: terms } = useApi<TermsProps>('/affiliates/terms/', { public: true });
  const [code, setCode] = useState('');
  const [website, setWebsite] = useState('');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  const share = terms ? Number(terms.revshare_percent) : 30;

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
        <h2 className="text-xl font-extrabold">Become an agent: earn {pct(share)} on every losing ticket</h2>
        <p className="mt-1 max-w-lg text-sm text-white/75">
          Bring customers with your link or code. Every time one of their tickets loses, you get {pct(share)} of what they staked. It’s free and you can never lose money.
        </p>
        <ol className="mt-4 grid gap-2 text-sm sm:grid-cols-3">
          {['Share your link or code', 'Customers sign up and bet', `You get ${pct(share)} of losing stakes`].map((step, i) => (
            <li key={step} className="flex items-center gap-2 rounded-xl bg-white/10 px-3 py-2">
              <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-white/20 text-xs font-extrabold">{i + 1}</span>{step}
            </li>
          ))}
        </ol>
      </div>
      <CardContent className="space-y-5 pt-6">
        {terms && <HowYouEarn a={terms} />}
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="space-y-1 text-sm">
            <span className="font-medium">Your code <span className="text-muted-foreground">(optional, customers type it at sign-up)</span></span>
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
          {busy ? <span className="inline-flex items-center justify-center gap-2"><Spinner size={14} />Joining…</span> : 'Become an agent'}
        </button>
      </CardContent>
    </Card>
  );
}

function MoneyChip({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-xl bg-white/10 px-3 py-2.5 backdrop-blur-sm">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-white/60">{label}</p>
      <p className="mt-0.5 text-base font-extrabold tabular-nums sm:text-lg">{value}</p>
    </div>
  );
}

function Stat({ icon, label, value, tone = '' }: { icon: React.ReactNode; label: string; value: string | number; tone?: string }) {
  return (
    <div className="rounded-xl border border-border bg-card p-3">
      <span className={`mb-1.5 block ${tone || 'text-secondary'}`}>{icon}</span>
      <p className={`text-xl font-extrabold tabular-nums ${tone}`}>{typeof value === 'number' ? value.toLocaleString() : value}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}

function commissionText(c: Commission) {
  if (c.kind === 'stake') {
    return { title: `Losing tickets · ${dayLabel(c.period)}`, sub: `${c.note ? `${c.note} · ` : ''}${pct(c.rate)} of ${money(c.base_amount)} staked` };
  }
  if (c.kind === 'cpa') {
    return { title: 'New customer bonus', sub: Number(c.rate) > 0 ? `${pct(c.rate)} of their ${money(c.base_amount)} first deposit` : 'A customer made their first deposit' };
  }
  return { title: `Share for ${monthLabel(c.period)}`, sub: `Customers lost ${money(c.base_amount)} · your ${pct(c.rate)}` };
}

type Tab = 'customers' | 'transactions' | 'withdrawals';

function Dashboard({ a, refetch }: { a: Affiliate & { stats: Stats }; refetch: () => void }) {
  const s = a.stats;
  const b = a.balance ?? { available: '0', pending: '0', in_payout: '0', paid_out: '0', carryover: '0' };
  const [payOpen, setPayOpen] = useState(false);
  const [tab, setTab] = useState<Tab>('customers');
  const p = a.programme;
  const welcome = p && Number(p.welcome_bonus_percent) > 0
    ? `${Number(p.welcome_bonus_percent)}%${Number(p.welcome_bonus_cap) > 0 ? ` (up to ${money(p.welcome_bonus_cap)})` : ''}` : undefined;
  const payouts = a.payouts ?? [];
  const commissions = a.commissions ?? [];
  const rate = Number(s.commission_rate ?? a.revshare_percent);
  const min = Number(a.payout_options?.min_payout ?? MIN_WITHDRAWAL);
  const canWithdraw = Number(b.available) >= min && !!a.payout_options;
  const t = s.tickets_today ?? { played: 0, won: 0, lost: 0, open: 0 };

  // Money in (commissions) and out (withdrawals), newest first.
  const transactions = useMemo(() => [
    ...commissions.filter((c) => c.status !== 'rejected').map((c) => ({
      key: `c${c.id}`, at: c.created_at, ...commissionText(c), amount: Number(c.amount),
      badge: <Badge variant={STATUS_BADGE[c.status]}>{STATUS_LABEL[c.status]}</Badge>,
    })),
    ...payouts.filter((po) => po.status !== 'rejected').map((po) => ({
      key: `p${po.id}`, at: po.created_at, title: `Withdrawal to ${po.method_label}`, sub: new Date(po.created_at).toLocaleDateString(),
      amount: -Number(po.amount), badge: <Badge variant={PAYOUT_BADGE[po.status]}>{PAYOUT_LABEL[po.status]}</Badge>,
    })),
  ].sort((x, y) => Date.parse(y.at) - Date.parse(x.at)), [commissions, payouts]);

  return (
    <div className="space-y-5">
      {/* My wallet */}
      <section className="overflow-hidden rounded-2xl bg-gradient-to-br from-primary via-primary to-secondary/80 p-5 text-white shadow-lg sm:p-6">
        <div className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.18em] text-white/60">My wallet · code {a.code}</p>
            <p className="mt-1 text-4xl font-extrabold tabular-nums sm:text-5xl">{money(b.available)}</p>
            <p className="mt-1 text-sm text-white/75">Minimum withdrawal {money(min)}. Withdraw any day.</p>
          </div>
          <button
            onClick={() => setPayOpen(true)}
            disabled={!canWithdraw}
            className="flex items-center gap-2 rounded-xl bg-win px-5 py-3 text-sm font-extrabold text-win-foreground shadow transition-transform hover:scale-[1.02] disabled:opacity-50 disabled:hover:scale-100"
          >
            Withdraw <FaArrowRight size={12} />
          </button>
        </div>
        <div className="mt-5 grid grid-cols-3 gap-2.5">
          <MoneyChip label="Being checked" value={money(b.pending)} />
          <MoneyChip label="On its way" value={money(b.in_payout)} />
          <MoneyChip label="Withdrawn" value={money(b.paid_out)} />
        </div>
      </section>

      {/* My commission */}
      <Card className="rounded-2xl">
        <CardContent className="space-y-3 pt-5">
          <div className="flex flex-wrap items-end justify-between gap-3">
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">My commission today</p>
              <p className="text-3xl font-extrabold tabular-nums text-win">{money(s.commission_today ?? 0)}</p>
            </div>
            <div className="flex gap-5 text-right">
              <div><p className="text-xs text-muted-foreground">This month</p><p className="font-extrabold tabular-nums">{money(s.commission_month ?? 0)}</p></div>
              <div><p className="text-xs text-muted-foreground">All time</p><p className="font-extrabold tabular-nums">{money(s.commission_total ?? 0)}</p></div>
            </div>
          </div>
          <p className="text-sm text-muted-foreground">
            You get <b className="text-foreground">{pct(rate)} of the stake on every ticket your customers lose</b>.
            {Number(s.losing_tickets_today) > 0
              ? <> Today {s.losing_tickets_today} losing ticket{s.losing_tickets_today === 1 ? '' : 's'} staked {money(s.lost_stakes_today)}. It’s added to your wallet after the day ends.</>
              : <> No losing tickets yet today.</>}
          </p>
        </CardContent>
      </Card>

      {/* Today’s tickets, clicks and sign-ups */}
      <section className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <h2 className="text-sm font-bold">Today</h2>
          <Link href="/account/affiliate/tickets" className="inline-flex items-center gap-1.5 rounded-lg bg-secondary px-3 py-1.5 text-xs font-bold text-secondary-foreground">
            <BsTicketPerforated size={13} /> View all tickets
          </Link>
        </div>
        <div className="grid grid-cols-3 gap-2 sm:grid-cols-5">
          <Stat icon={<BsTicketPerforated size={16} />} label="Tickets played" value={t.played} />
          <Stat icon={<BsCheckCircleFill size={16} />} label="Tickets won" value={t.won} tone="text-win" />
          <Stat icon={<BsXCircleFill size={16} />} label="Tickets lost" value={t.lost} tone="text-down" />
          <Stat icon={<BsLink45Deg size={16} />} label="Link clicks" value={s.clicks_total} />
          <Stat icon={<BsPersonPlus size={16} />} label="Sign-ups" value={s.signups} />
        </div>
      </section>

      <Card className="rounded-2xl">
        <CardHeader className="pb-0">
          <div className="-mx-1 flex gap-1 overflow-x-auto px-1" role="tablist">
            {([['customers', `My customers (${s.signups})`], ['transactions', `Transactions (${transactions.length})`],
              ['withdrawals', `Withdrawals (${payouts.length})`]] as [Tab, string][]).map(([id, label]) => (
              <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
                className={`shrink-0 border-b-2 px-3 py-2 text-sm font-bold transition-colors ${tab === id ? 'border-secondary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
                {label}
              </button>
            ))}
          </div>
        </CardHeader>
        <CardContent className="pt-4">
          {tab === 'customers' && (s.referrals.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">Nobody has joined with your link yet. Share it below.</p>
          ) : (
            <ul className="divide-y divide-border">
              {s.referrals.map((r, i) => (
                <li key={i} className="flex items-center justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold">{r.player}</p>
                    <p className="text-xs text-muted-foreground">Joined {new Date(r.joined).toLocaleDateString()}{r.campaign && ` · via ${r.campaign}`}</p>
                  </div>
                  <Badge variant={r.deposited ? 'default' : 'secondary'}>{r.deposited ? 'Deposited' : 'No deposit yet'}</Badge>
                </li>
              ))}
            </ul>
          ))}

          {tab === 'transactions' && (transactions.length === 0 ? (
            <p className="py-4 text-sm text-muted-foreground">Nothing yet. Your commission shows here each day your customers have losing tickets.</p>
          ) : (
            <ul className="divide-y divide-border">
              {transactions.map((x) => (
                <li key={x.key} className="flex items-start justify-between gap-3 py-3">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold">{x.title}</p>
                    <p className="text-xs text-muted-foreground">{x.sub}</p>
                  </div>
                  <div className="shrink-0 text-right">
                    <p className={`font-bold tabular-nums ${x.amount >= 0 ? 'text-win' : ''}`}>{x.amount >= 0 ? '+' : '−'}{money(Math.abs(x.amount))}</p>
                    {x.badge}
                  </div>
                </li>
              ))}
            </ul>
          ))}

          {tab === 'withdrawals' && (payouts.length === 0 ? (
            <p className="flex items-center gap-2 py-4 text-sm text-muted-foreground"><FaClockRotateLeft /> No withdrawals yet. You can withdraw once your wallet reaches {money(min)}.</p>
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

      {/* Kept so the agent can still bring in customers. */}
      <details className="group rounded-2xl border border-border bg-card">
        <summary className="flex cursor-pointer list-none items-center justify-between gap-2 px-5 py-4 text-sm font-bold">
          My link to share
          <BsLink45Deg size={14} className="text-muted-foreground" />
        </summary>
        <div className="border-t border-border p-4"><ShareLink code={a.code} welcome={welcome} /></div>
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
      <h1 className="text-2xl font-bold">Agent dashboard</h1>
      {loading && !data ? (
        <LoadingState />
      ) : notJoined ? (
        <Apply onDone={refetch} />
      ) : error ? (
        <p className="text-sm text-destructive">Couldn’t load your agent account. <button onClick={refetch} className="underline">Retry</button></p>
      ) : data?.status === 'active' && data.stats ? (
        <Dashboard a={data as Affiliate & { stats: Stats }} refetch={refetch} />
      ) : data ? (
        <Card className="rounded-2xl">
          <CardContent className="space-y-2 pt-6">
            <p className="font-bold">
              {data.status === 'pending' ? 'Thanks, we’re checking your request' : data.status === 'suspended' ? 'Your agent account is paused' : 'Request not approved'}
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
