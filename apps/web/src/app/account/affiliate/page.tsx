'use client';

import { useState } from 'react';
import { FaHandshake } from 'react-icons/fa';
import { FaArrowRight, FaCheck, FaClockRotateLeft, FaCopy, FaLock, FaLockOpen } from 'react-icons/fa6';
import { BsCashStack, BsGraphDownArrow, BsLink45Deg, BsPeople, BsPersonCheck, BsPersonPlus, BsTicketPerforated, BsTrophy } from 'react-icons/bs';
import { Card, CardContent } from '@slyk/ui/components/card';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';
import { LoadingState, Spinner } from '@slyk/ui/components/spinner';
import Link from 'next/link';
import { PayoutDialog, type PayoutOptions } from '@/components/affiliate/payout-dialog';
import { PeriodReport } from '@/components/affiliate/period-report';
import { ShareLink } from '@/components/affiliate/share-link';

interface Commission {
  id: number;
  kind: 'stake' | 'netloss' | 'revshare' | 'cpa' | 'prize' | 'adjust';
  period: string | null;
  ticket?: string;
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
  commission_basis?: 'net_loss' | 'stake';
  lost_stakes_today: string;
  losing_tickets_today: number;
  net_loss_today?: string;
  carried_in?: string;
  aviator_commission_rate?: string;
  commission_today: string;
  commission_month: string;
  commission_last_month?: string;
  commission_total: string;
  deposits_this_month?: string;
  depositors_this_month?: number;
  signups_this_month?: number;
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
  balance?: { available: string; locked?: string; unlocks_on?: string | null; pending: string; in_payout: string; paid_out: string; carryover: string };
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

const STATUS_LABEL: Record<Commission['status'], string> = {
  pending: 'Being checked', approved: 'In your balance', paid: 'Paid to you', rejected: 'Not approved',
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
      <p>Every night your commission for the day before — your share of what your customers lost on sports (and a smaller share on Aviator and casino games) — is added to your agent wallet. <b className="text-foreground">It stays there until the month ends; from the 1st you can move it to your Winnings wallet or withdraw it.</b></p>
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
      <div className="bg-gradient-to-br from-primary via-primary to-[#0B3BB8] px-6 py-7 text-white">
        <FaHandshake size={28} className="mb-3 text-gold" />
        <h2 className="text-xl font-extrabold">Become an agent: earn {pct(share)} of what your customers lose</h2>
        <p className="mt-1 max-w-lg text-sm text-white/75">
          Bring customers with your link or code. You get {pct(share)} of what they lose on sports (stakes minus winnings), and a smaller share on Aviator and casino games, added to your agent wallet every night and unlocked at the end of each month. It’s free and you can never lose money.
        </p>
        <ol className="mt-4 grid gap-2 text-sm sm:grid-cols-3">
          {['Share your link or code', 'Customers sign up and bet', `You get ${pct(share)} of their sports net losses`].map((step, i) => (
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

const shortDate = (iso: string) => new Date(`${iso.slice(0, 10)}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });

// Commissions reversed by the old deposit-commission check carry this note prefix.
const REVERSED = 'CPA clawback';
const signedMoney = (v: string | number) => (Number(v) < 0 ? `−${money(Math.abs(Number(v)))}` : money(v));

function commissionText(c: Commission) {
  if (c.kind === 'netloss') {
    return { title: `Customers’ net loss · ${dayLabel(c.period)}`, sub: `${pct(c.rate)} of ${money(c.base_amount)} lost by ${c.active_players} customer${c.active_players === 1 ? '' : 's'}` };
  }
  if (c.kind === 'stake') {
    return { title: `Losing ticket ${c.ticket ?? ''} · ${dayLabel(c.period)}`, sub: `${pct(c.rate)} of the ${money(c.base_amount)} stake` };
  }
  if (c.kind === 'prize') {
    return { title: `🏆 ${c.note.replace(/^Competition:\s*/, '') || 'Competition prize'}`, sub: 'Competition prize, added to your locked balance' };
  }
  if (c.kind === 'adjust') {
    return { title: Number(c.amount) < 0 ? 'Balance adjustment' : 'Bonus added by the team', sub: c.note || 'Adjusted by the team' };
  }
  if (c.kind === 'cpa' && c.note.startsWith(REVERSED)) {
    return { title: 'New customer bonus · reversed', sub: 'The customer didn’t play their first deposit through with their own money' };
  }
  if (c.kind === 'cpa') {
    return { title: 'New customer bonus', sub: Number(c.rate) > 0 ? `${pct(c.rate)} of their ${money(c.base_amount)} first deposit` : 'A customer made their first deposit' };
  }
  return { title: `Share for ${monthLabel(c.period)}`, sub: `Customers lost ${money(c.base_amount)} · your ${pct(c.rate)}` };
}

type Tab = 'earnings' | 'customers' | 'withdrawals' | 'reports';

interface Paged<T> { count: number; results: T[] }
interface Customer { player: string; joined: string; campaign: string; deposited: boolean }
const PAGE = 25;

function PagerBar({ page, count, onPage }: { page: number; count: number; onPage: (p: number) => void }) {
  const pages = Math.max(1, Math.ceil(count / PAGE));
  if (pages <= 1) return null;
  const from = (page - 1) * PAGE + 1;
  return (
    <div className="flex items-center justify-between gap-3 border-t border-border pt-3 text-xs text-muted-foreground">
      <span>{from}–{Math.min(page * PAGE, count)} of {count.toLocaleString()}</span>
      <div className="flex gap-2">
        <button disabled={page <= 1} onClick={() => onPage(page - 1)} className="rounded-lg border border-border px-3 py-1.5 font-bold disabled:opacity-40">Previous</button>
        <button disabled={page >= pages} onClick={() => onPage(page + 1)} className="rounded-lg border border-border px-3 py-1.5 font-bold disabled:opacity-40">Next</button>
      </div>
    </div>
  );
}

function Empty({ children }: { children: React.ReactNode }) {
  return <p className="flex items-center gap-2 py-6 text-sm text-muted-foreground">{children}</p>;
}

/** Every customer linked to the agent, a page at a time (nobody hidden). */
function CustomersList() {
  const [page, setPage] = useState(1);
  const [q, setQ] = useState('');
  const { data, loading } = useApi<Paged<Customer>>(
    `/affiliates/me/customers/?page=${page}&page_size=${PAGE}${q.trim() ? `&q=${encodeURIComponent(q.trim())}` : ''}`);
  return (
    <div className="space-y-3">
      <input value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} placeholder="Find a customer"
        className="w-full rounded-lg border border-border bg-background px-3 py-2 text-sm outline-none focus:ring-2 focus:ring-ring" />
      {loading && !data ? <LoadingState className="py-4" label="Loading customers…" /> : !data?.results.length ? (
        <Empty>{q ? 'No customer matches.' : 'Nobody has joined with your link yet.'}</Empty>
      ) : (
        <ul className="divide-y divide-border">
          {data.results.map((r, i) => (
            <li key={`${page}-${i}`} className="flex items-center justify-between gap-3 py-3">
              <div className="min-w-0">
                <p className="truncate text-sm font-semibold">{r.player}</p>
                <p className="text-xs text-muted-foreground">Joined {new Date(r.joined).toLocaleDateString()}{r.campaign && ` · via ${r.campaign}`}</p>
              </div>
              <span className={`shrink-0 text-xs font-bold ${r.deposited ? 'text-win' : 'text-muted-foreground'}`}>
                {r.deposited ? 'Deposited' : 'No deposit yet'}
              </span>
            </li>
          ))}
        </ul>
      )}
      <PagerBar page={page} count={data?.count ?? 0} onPage={setPage} />
    </div>
  );
}

/** Every commission earned, newest first. */
function EarningsList() {
  const [page, setPage] = useState(1);
  const { data, loading } = useApi<Paged<Commission>>(`/affiliates/me/history/?kind=commissions&page=${page}&page_size=${PAGE}`);
  return (
    <div className="space-y-3">
      {loading && !data ? <LoadingState className="py-4" label="Loading earnings…" /> : !data?.results.length ? (
        <Empty>Nothing yet. Each day’s commission appears here the next morning.</Empty>
      ) : (
        <ul className="divide-y divide-border">
          {data.results.map((c) => {
            const t = commissionText(c);
            const rejected = c.status === 'rejected';
            return (
              <li key={c.id} className="flex items-start justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-semibold">{t.title}</p>
                  <p className="text-xs text-muted-foreground">{t.sub}</p>
                </div>
                <div className="shrink-0 text-right">
                  <p className={`font-bold tabular-nums ${rejected ? 'text-muted-foreground line-through' : Number(c.amount) < 0 ? 'text-destructive' : 'text-win'}`}>
                    {rejected ? money(c.amount) : Number(c.amount) < 0 ? signedMoney(c.amount) : `+${money(c.amount)}`}
                  </p>
                  <p className="text-[11px] font-semibold text-muted-foreground">{STATUS_LABEL[c.status]}</p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <PagerBar page={page} count={data?.count ?? 0} onPage={setPage} />
    </div>
  );
}

/** Every move to Winnings and every withdrawal, newest first. */
function WithdrawalsList({ min }: { min: number }) {
  const [page, setPage] = useState(1);
  const { data, loading } = useApi<Paged<Payout>>(`/affiliates/me/history/?kind=payouts&page=${page}&page_size=${PAGE}`);
  return (
    <div className="space-y-3">
      {loading && !data ? <LoadingState className="py-4" label="Loading withdrawals…" /> : !data?.results.length ? (
        <Empty><FaClockRotateLeft /> No withdrawals yet. You can withdraw once your balance reaches {money(min)}.</Empty>
      ) : (
        <ul className="divide-y divide-border">
          {data.results.map((po) => {
            const correction = po.note.startsWith(REVERSED);
            return (
              <li key={po.id} className="flex items-start justify-between gap-3 py-3">
                <div className="min-w-0">
                  <p className="text-sm font-semibold">
                    {correction ? 'Commission correction'
                      : po.method === 'wallet' ? 'Moved to your Winnings wallet'
                        : <>To {po.method_label}{po.account_number && <span className="ml-1.5 font-mono text-xs text-muted-foreground">···{po.account_number.slice(-4)}</span>}</>}
                  </p>
                  <p className="text-xs text-muted-foreground">
                    {new Date(po.created_at).toLocaleDateString()}
                    {!correction && (po.reference || po.note) && ` · ${po.status === 'paid' ? `Ref ${po.reference}` : po.note}`}
                  </p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="font-bold tabular-nums">{signedMoney(po.amount)}</p>
                  <p className="text-[11px] font-semibold text-muted-foreground">{correction ? 'Correction' : PAYOUT_LABEL[po.status]}</p>
                </div>
              </li>
            );
          })}
        </ul>
      )}
      <PagerBar page={page} count={data?.count ?? 0} onPage={setPage} />
    </div>
  );
}

interface CompetitionView {
  id: number; name: string; description: string; starts_on: string; ends_on: string; target_customers: number;
  target_deposits: string; min_customer_deposit: string; prize: string; status: 'upcoming' | 'running' | 'ended' | 'off';
  my: { customers: number; deposits: string; reached: boolean; percent: number }; won: boolean;
}

function Bar({ label, value, target, text }: { label: string; value: number; target: number; text: string }) {
  const pctDone = Math.min(100, Math.round((value / target) * 100));
  return (
    <div>
      <div className="flex items-center justify-between text-xs">
        <span className="text-muted-foreground">{label}</span>
        <span className="font-semibold tabular-nums">{text}</span>
      </div>
      <div className="mt-1 h-2 overflow-hidden rounded-full bg-muted" role="progressbar" aria-valuenow={pctDone} aria-valuemin={0} aria-valuemax={100} aria-label={label}>
        <div className={`h-full rounded-full ${pctDone >= 100 ? 'bg-win' : 'bg-secondary'}`} style={{ width: `${pctDone}%` }} />
      </div>
    </div>
  );
}

/** Competitions set by the team: targets for new customers and/or their deposits, with the agent's own progress.
 *  The prize is added automatically to the locked balance when a target is reached. */
function Competitions() {
  const { data } = useApi<{ competitions: CompetitionView[] }>('/affiliates/me/competitions/');
  const list = (data?.competitions ?? []).filter((c) => c.status !== 'off');
  if (list.length === 0) return null;
  const day = (iso: string) => new Date(`${iso}T00:00:00`).toLocaleDateString(undefined, { day: 'numeric', month: 'short' });
  return (
    <section>
      <h2 className="mb-2 text-sm font-bold">Competitions</h2>
      <div className="grid gap-3 lg:grid-cols-2">
        {list.map((c) => (
          <Card key={c.id} className={`rounded-2xl ${c.won ? 'border-win/50' : ''}`}>
            <CardContent className="space-y-3 pt-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="font-extrabold">🏆 {c.name}</p>
                  <p className="text-xs text-muted-foreground">{day(c.starts_on)} – {day(c.ends_on)} · {c.status === 'running' ? 'running now' : c.status === 'upcoming' ? 'starts soon' : 'ended'}</p>
                </div>
                <div className="shrink-0 text-right">
                  <p className="text-lg font-extrabold tabular-nums text-win">{money(c.prize)}</p>
                  <p className="text-[11px] text-muted-foreground">prize</p>
                </div>
              </div>
              {c.description && <p className="text-xs text-muted-foreground">{c.description}</p>}
              {c.target_customers > 0 && (
                <Bar label={`New customers${Number(c.min_customer_deposit) > 0 ? ` (each deposits ${money(c.min_customer_deposit)}+)` : ''}`}
                  value={c.my.customers} target={c.target_customers} text={`${c.my.customers} / ${c.target_customers}`} />
              )}
              {Number(c.target_deposits) > 0 && (
                <Bar label="Your customers’ deposits" value={Number(c.my.deposits)} target={Number(c.target_deposits)}
                  text={`${money(c.my.deposits)} / ${money(c.target_deposits)}`} />
              )}
              <p className={`text-xs font-semibold ${c.won ? 'text-win' : 'text-muted-foreground'}`}>
                {c.won ? `✓ You won ${money(c.prize)}. It’s in your locked balance.`
                  : c.status === 'ended' ? 'Ended without reaching the target.'
                    : `${c.my.percent}% of the way. Reach every target and the ${money(c.prize)} is added to your locked balance automatically.`}
              </p>
            </CardContent>
          </Card>
        ))}
      </div>
    </section>
  );
}

function HeroChip({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="min-w-0 rounded-xl bg-white/10 px-3 py-2.5">
      <p className="text-[11px] font-semibold uppercase tracking-wide text-white/60">{label}</p>
      <p className="mt-0.5 truncate text-base font-extrabold tabular-nums sm:text-lg">{value}</p>
      {hint && <p className="text-[10.5px] text-white/55">{hint}</p>}
    </div>
  );
}

function Kpi({ icon, label, value, sub }: { icon: React.ReactNode; label: string; value: string | number; sub?: string }) {
  return (
    <div className="min-w-0 rounded-xl border border-border bg-card p-3">
      <div className="flex items-center gap-1.5 text-muted-foreground">
        <span className="text-secondary">{icon}</span>
        <span className="truncate text-xs font-semibold">{label}</span>
      </div>
      <p className="mt-1.5 truncate text-xl font-extrabold tabular-nums">{typeof value === 'number' ? value.toLocaleString() : value}</p>
      {sub && <p className="truncate text-[11px] text-muted-foreground">{sub}</p>}
    </div>
  );
}

function CopyCode({ code }: { code: string }) {
  const [copied, setCopied] = useState(false);
  async function copy() {
    try { await navigator.clipboard.writeText(code); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* no clipboard */ }
  }
  return (
    <button onClick={copy} className="inline-flex items-center gap-2 rounded-lg border border-border bg-card px-3 py-1.5 text-sm" aria-label={`Copy your code ${code}`}>
      <span className="text-muted-foreground">Code</span>
      <span className="font-mono font-extrabold">{code}</span>
      {copied ? <FaCheck size={11} className="text-win" /> : <FaCopy size={11} className="text-muted-foreground" />}
    </button>
  );
}

function Dashboard({ a, refetch }: { a: Affiliate & { stats: Stats }; refetch: () => void }) {
  const s = a.stats;
  const b = a.balance ?? { available: '0', pending: '0', in_payout: '0', paid_out: '0', carryover: '0' };
  const [payOpen, setPayOpen] = useState(false);
  const [tab, setTab] = useState<Tab>('earnings');
  const p = a.programme;
  const welcome = p && Number(p.welcome_bonus_percent) > 0
    ? `${Number(p.welcome_bonus_percent)}%${Number(p.welcome_bonus_cap) > 0 ? ` (up to ${money(p.welcome_bonus_cap)})` : ''}` : undefined;
  const rate = Number(s.commission_rate ?? a.revshare_percent);
  const min = Number(a.payout_options?.min_payout ?? MIN_WITHDRAWAL);
  const canWithdraw = Number(b.available) >= min && !!a.payout_options;
  const held = Number(b.locked ?? 0);
  const netLoss = Number(s.net_loss_today ?? 0);
  const perTicket = s.commission_basis === 'stake';
  const aviatorRate = Number(s.aviator_commission_rate ?? 0);
  // With automatic payout, final earnings go straight to the Winnings wallet.
  const auto = !!a.payout_options?.auto_payout && Number(b.available) < 0.01;
  const daysLeft = b.unlocks_on
    ? Math.max(0, Math.ceil((Date.parse(`${b.unlocks_on.slice(0, 10)}T00:00:00`) - Date.now()) / 86_400_000)) : null;
  const monthName = new Date().toLocaleDateString(undefined, { month: 'long' });
  const lastMonth = Number(s.commission_last_month ?? 0);
  const trend = lastMonth > 0 ? Math.round(((Number(s.commission_month ?? 0) - lastMonth) / lastMonth) * 100) : null;
  const conversion = s.signups > 0 ? Math.round((s.depositors / s.signups) * 100) : null;
  const perActive = s.active_this_month > 0 ? Number(s.commission_month ?? 0) / s.active_this_month : null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Agent dashboard</h1>
        <CopyCode code={a.code} />
      </div>

      {/* Balance: this month's earnings first, and when they unlock */}
      <section className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-primary via-primary to-[#0B3BB8] p-5 text-white shadow-lg sm:p-6">
        {held > 0 && (
          <FaLock aria-hidden className="pointer-events-none absolute -right-8 -top-8 h-44 w-44 text-white/[0.06] sm:h-56 sm:w-56" />
        )}
        <div className="relative flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-[0.16em] text-white/65">Earned in {monthName}</p>
            <p className="mt-1 text-4xl font-extrabold tabular-nums sm:text-5xl">{money(s.commission_month ?? 0)}</p>
            {lastMonth > 0 && (
              <p className="mt-1 text-sm text-white/75">
                {money(lastMonth)} last month
                {trend != null && <span className={`ml-2 rounded-full px-2 py-0.5 text-xs font-bold ${trend >= 0 ? 'bg-win/30' : 'bg-white/15'}`}>
                  {trend >= 0 ? '▲' : '▼'} {Math.abs(trend)}%</span>}
              </p>
            )}
          </div>
          {held > 0 && b.unlocks_on && (
            <div className="flex items-center gap-3 rounded-2xl bg-black/20 px-3 py-2.5 ring-1 ring-white/15">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gold text-gold-foreground shadow-md">
                <FaLock size={16} />
              </span>
              <div className="leading-tight">
                <p className="text-sm font-extrabold">{money(held)} locked</p>
                <p className="text-xs text-white/75">
                  Opens {shortDate(b.unlocks_on)}{daysLeft != null && ` · ${daysLeft === 0 ? 'today' : daysLeft === 1 ? 'tomorrow' : `in ${daysLeft} days`}`}
                </p>
              </div>
            </div>
          )}
        </div>

        <div className="relative mt-4 flex flex-wrap items-center justify-between gap-3">
          <div className="flex flex-wrap gap-2 text-sm">
            <span className="inline-flex items-center gap-1.5 rounded-full bg-win/25 px-3 py-1 font-bold">
              <FaLockOpen size={11} /> {money(b.available)} available now
            </span>
          </div>
          {auto ? (
            <Link href="/account/wallet" className="inline-flex items-center gap-2 rounded-xl bg-win px-5 py-2.5 text-sm font-extrabold text-win-foreground shadow">
              Go to wallet <FaArrowRight size={12} />
            </Link>
          ) : (
            <button onClick={() => setPayOpen(true)} disabled={!canWithdraw}
              className="inline-flex items-center gap-2 rounded-xl bg-win px-5 py-2.5 text-sm font-extrabold text-win-foreground shadow disabled:opacity-60">
              {canWithdraw ? <>Withdraw <FaArrowRight size={12} /></>
                : held > 0 && b.unlocks_on ? <><FaLock size={11} /> Opens {shortDate(b.unlocks_on)}</>
                  : <>Withdraw · min {money(min)}</>}
            </button>
          )}
        </div>
        <p className="relative mt-3 text-xs text-white/70">
          {auto
            ? 'Once unlocked, your commission is paid straight into your Winnings wallet.'
            : held > 0
              ? `This month’s earnings stay locked until the month ends. From ${b.unlocks_on ? shortDate(b.unlocks_on) : 'the 1st'} you can move them to your Winnings wallet or withdraw (minimum ${money(min)}).`
              : `Move it to your Winnings wallet or withdraw it (minimum ${money(min)}).`}
        </p>

        <div className="relative mt-4 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          <HeroChip label="Today so far" value={money(s.commission_today ?? 0)} hint={perTicket ? undefined : 'added after midnight'} />
          <HeroChip label="Being sent" value={money(b.in_payout)} hint={Number(b.pending) > 0 ? `${money(b.pending)} being checked` : undefined} />
          <HeroChip label="Paid to you" value={money(b.paid_out)} hint="all time" />
          <HeroChip label="Earned all time" value={money(s.commission_total ?? 0)} />
        </div>
      </section>

      {/* KPIs */}
      <section>
        <h2 className="mb-2 text-sm font-bold">Your numbers this month</h2>
        <div className="grid grid-cols-2 gap-2.5 lg:grid-cols-4">
          <Kpi icon={<BsGraphDownArrow size={15} />} label="Customers’ net loss" value={money(s.ngr_this_month ?? 0)}
            sub={`you earn ${pct(rate)} on sports`} />
          <Kpi icon={<BsCashStack size={15} />} label="Customer deposits" value={money(s.deposits_this_month ?? 0)}
            sub={`${s.depositors_this_month ?? 0} customer${s.depositors_this_month === 1 ? '' : 's'} deposited`} />
          <Kpi icon={<BsPeople size={15} />} label="Active customers" value={s.active_this_month}
            sub={`of ${s.signups.toLocaleString()} total`} />
          <Kpi icon={<BsPersonPlus size={15} />} label="New sign-ups" value={s.signups_this_month ?? 0}
            sub={`${s.signups.toLocaleString()} all time`} />
          <Kpi icon={<BsPersonCheck size={15} />} label="Deposit rate" value={conversion != null ? `${conversion}%` : '—'}
            sub={`${s.depositors} of ${s.signups} sign-ups deposited`} />
          <Kpi icon={<BsLink45Deg size={15} />} label="Link clicks (30 days)" value={s.clicks_30d}
            sub={`${s.clicks_total.toLocaleString()} all time`} />
          <Kpi icon={<BsTicketPerforated size={15} />} label="Tickets today" value={s.tickets_today?.played ?? 0}
            sub={s.tickets_today ? `${s.tickets_today.won} won · ${s.tickets_today.lost} lost · ${s.tickets_today.open} open` : undefined} />
          <Kpi icon={<BsTrophy size={15} />} label="Per active customer" value={perActive != null ? money(perActive) : '—'}
            sub="your commission this month" />
        </div>
      </section>

      {/* How today's commission is worked out */}
      <Card className="rounded-2xl">
        <CardContent className="pt-5">
          <p className="text-sm font-bold">How your commission is worked out</p>
          <dl className="mt-3 divide-y divide-border text-sm">
            {perTicket ? (
              <div className="flex items-center justify-between gap-3 py-2">
                <dt className="shrink-0 text-muted-foreground">Losing tickets today</dt>
                <dd className="text-right font-semibold tabular-nums">
                  {s.losing_tickets_today} ticket{s.losing_tickets_today === 1 ? '' : 's'} · {money(s.lost_stakes_today)} staked
                </dd>
              </div>
            ) : (
              <div className="flex items-center justify-between gap-3 py-2">
                <dt className="shrink-0 text-muted-foreground">Your customers’ result today</dt>
                <dd className="font-semibold tabular-nums">{netLoss >= 0 ? `lost ${money(netLoss)}` : `won ${money(Math.abs(netLoss))}`}</dd>
              </div>
            )}
            {!perTicket && Number(s.carried_in ?? 0) !== 0 && (
              <div className="flex items-center justify-between gap-3 py-2">
                <dt className="shrink-0 text-muted-foreground">{Number(s.carried_in) < 0 ? 'Customers’ wins still to earn back' : 'Carried from earlier days'}</dt>
                <dd className="font-semibold tabular-nums">{signedMoney(s.carried_in ?? 0)}</dd>
              </div>
            )}
            <div className="flex items-center justify-between gap-3 py-2">
              <dt className="shrink-0 text-muted-foreground">Your share</dt>
              <dd className="text-right font-semibold">
                {perTicket ? <>{pct(rate)} of each losing stake</> : <>{pct(rate)} on sports</>}
                {aviatorRate > 0 && <> · {pct(aviatorRate)} on Aviator & casino</>}
              </dd>
            </div>
            <div className="flex items-center justify-between gap-3 py-2">
              <dt className="shrink-0 font-semibold">Your commission today so far</dt>
              <dd className="font-extrabold tabular-nums text-win">{money(s.commission_today ?? 0)}</dd>
            </div>
          </dl>
          <p className="mt-2 text-xs text-muted-foreground">
            {perTicket
              ? 'Each losing ticket is credited a few minutes after it settles. Winning tickets cost you nothing.'
              : 'Net loss = stakes minus winnings, added up each day and credited after midnight. If your customers win overall on a day, that amount comes off the next days’ commission first.'}
          </p>
        </CardContent>
      </Card>

      <Competitions />

      {/* Activity */}
      <Card className="rounded-2xl">
        <div className="-mb-px flex gap-1 overflow-x-auto border-b border-border px-3 pt-2" role="tablist">
          {([['earnings', 'Earnings'], ['customers', 'Customers'], ['withdrawals', 'Withdrawals'], ['reports', 'Reports']] as [Tab, string][]).map(([id, label]) => (
            <button key={id} role="tab" aria-selected={tab === id} onClick={() => setTab(id)}
              className={`shrink-0 border-b-2 px-3 py-2.5 text-sm font-bold transition-colors ${tab === id ? 'border-secondary text-foreground' : 'border-transparent text-muted-foreground hover:text-foreground'}`}>
              {label}
            </button>
          ))}
        </div>
        <CardContent className="pt-4">
          {tab === 'earnings' && <EarningsList />}
          {tab === 'customers' && <CustomersList />}
          {tab === 'withdrawals' && <WithdrawalsList min={min} />}
          {tab === 'reports' && <PeriodReport />}
        </CardContent>
      </Card>

      {/* Bring in customers */}
      <Card className="rounded-2xl">
        <CardContent className="space-y-3 pt-5">
          <p className="text-sm font-bold">Share your link</p>
          <ShareLink code={a.code} welcome={welcome} />
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
      {!(data?.status === 'active' && data.stats) && <h1 className="text-2xl font-bold">Agent dashboard</h1>}
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
