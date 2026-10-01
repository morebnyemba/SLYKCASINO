'use client';

import { useState } from 'react';
import { FaCheck, FaCopy, FaHandshake } from 'react-icons/fa';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';

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

interface Stats {
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

interface Affiliate {
  code: string;
  status: 'pending' | 'active' | 'suspended' | 'rejected';
  revshare_percent: string;
  cpa_amount: string;
  cpa_min_deposit: string;
  stats?: Stats;
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
  pending: 'secondary', approved: 'secondary', paid: 'default', rejected: 'destructive',
};

function Terms({ a }: { a: Pick<Affiliate, 'revshare_percent' | 'cpa_amount' | 'cpa_min_deposit'> }) {
  return (
    <ul className="space-y-1.5 text-sm text-muted-foreground">
      <li><b className="text-foreground">{pct(a.revshare_percent)}</b> of the net gaming revenue of every player you refer, paid monthly.</li>
      {Number(a.cpa_amount) > 0 && (
        <li><b className="text-foreground">{money(a.cpa_amount)}</b> for each referral who deposits {money(a.cpa_min_deposit)} or more.</li>
      )}
      <li>Commission is paid into your wallet balance once approved. A losing month pays nothing and isn’t carried over.</li>
    </ul>
  );
}

function Apply({ onDone }: { onDone: () => void }) {
  const { accessToken } = useAuth();
  const { data: terms } = useApi<Pick<Affiliate, 'revshare_percent' | 'cpa_amount' | 'cpa_min_deposit'>>('/affiliates/terms/', { public: true });
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
          {busy ? 'Applying…' : 'Join the affiliate programme'}
        </button>
      </CardContent>
    </Card>
  );
}

function Stat({ label, value, hint }: { label: string; value: string | number; hint?: string }) {
  return (
    <div className="rounded-xl border border-border bg-card p-4">
      <p className="text-xs font-semibold text-muted-foreground">{label}</p>
      <p className="mt-1 text-xl font-extrabold tabular-nums">{value}</p>
      {hint && <p className="mt-0.5 text-[11px] text-muted-foreground">{hint}</p>}
    </div>
  );
}

function Dashboard({ a }: { a: Affiliate & { stats: Stats } }) {
  const s = a.stats;
  const origin = typeof window !== 'undefined' ? window.location.origin : '';
  const [campaign, setCampaign] = useState('');
  const link = `${origin}/?ref=${a.code}${campaign ? `&campaign=${encodeURIComponent(campaign)}` : ''}`;
  const [copied, setCopied] = useState(false);

  async function copy() {
    try { await navigator.clipboard.writeText(link); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* no clipboard */ }
  }

  return (
    <div className="space-y-6">
      <Card className="rounded-2xl">
        <CardContent className="space-y-3 pt-6">
          <p className="text-sm font-bold">Your referral link</p>
          <div className="flex flex-col gap-2 sm:flex-row">
            <code className="min-w-0 flex-1 truncate rounded-lg border border-border bg-input px-3 py-2.5 text-sm">{link}</code>
            <button onClick={copy} className="flex items-center justify-center gap-2 rounded-lg bg-secondary px-4 py-2.5 text-sm font-bold text-white">
              {copied ? <FaCheck size={12} /> : <FaCopy size={12} />} {copied ? 'Copied' : 'Copy link'}
            </button>
          </div>
          <div className="flex flex-wrap items-center gap-2 text-xs text-muted-foreground">
            <span>Code <b className="text-foreground">{a.code}</b> — players can also enter it at sign-up.</span>
            <input
              value={campaign}
              onChange={(e) => setCampaign(e.target.value.replace(/[^A-Za-z0-9_-]/g, '').slice(0, 50))}
              placeholder="campaign tag (optional)"
              className="ml-auto rounded-md border border-border bg-input px-2 py-1 text-xs outline-none"
            />
          </div>
        </CardContent>
      </Card>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Stat label="Clicks (30 days)" value={s.clicks_30d} hint={`${s.clicks_total} all time`} />
        <Stat label="Sign-ups" value={s.signups} hint={`${s.depositors} deposited`} />
        <Stat label="This month’s revenue" value={money(s.ngr_this_month)} hint={`${s.active_this_month} active player${s.active_this_month === 1 ? '' : 's'}`} />
        <Stat label="Estimated commission" value={money(s.estimated_commission)} hint={`${pct(a.revshare_percent)} share, paid after month end`} />
      </div>
      <div className="grid grid-cols-2 gap-3">
        <Stat label="Awaiting payment" value={money(s.pending)} />
        <Stat label="Paid to your wallet" value={money(s.paid)} />
      </div>

      <Card className="rounded-2xl">
        <CardHeader><CardTitle className="text-base">Your terms</CardTitle></CardHeader>
        <CardContent><Terms a={a} /></CardContent>
      </Card>

      <Card className="rounded-2xl">
        <CardHeader><CardTitle className="text-base">Commissions</CardTitle></CardHeader>
        <CardContent>
          {(a.commissions ?? []).length === 0 ? (
            <p className="text-sm text-muted-foreground">No commissions yet — revenue share is calculated after each month closes.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="text-left text-xs text-muted-foreground">
                  <tr><th className="py-2">For</th><th>Based on</th><th className="text-right">Amount</th><th className="text-right">Status</th></tr>
                </thead>
                <tbody>
                  {a.commissions!.map((c) => (
                    <tr key={c.id} className="border-t border-border">
                      <td className="py-2.5">{c.kind === 'cpa' ? 'New depositor (CPA)' : monthLabel(c.period)}</td>
                      <td className="text-muted-foreground">
                        {c.kind === 'cpa' ? `${money(c.base_amount)} deposited` : `${money(c.base_amount)} revenue × ${pct(c.rate)}`}
                      </td>
                      <td className="text-right font-bold tabular-nums">{money(c.amount)}</td>
                      <td className="text-right"><Badge variant={STATUS_BADGE[c.status]}>{c.status}</Badge></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      <Card className="rounded-2xl">
        <CardHeader><CardTitle className="text-base">Referred players</CardTitle></CardHeader>
        <CardContent>
          {s.referrals.length === 0 ? (
            <p className="text-sm text-muted-foreground">Nobody has signed up through your link yet.</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
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
          )}
        </CardContent>
      </Card>
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
        <p className="text-sm text-muted-foreground">Loading…</p>
      ) : notJoined ? (
        <Apply onDone={refetch} />
      ) : error ? (
        <p className="text-sm text-destructive">Couldn’t load your affiliate account. <button onClick={refetch} className="underline">Retry</button></p>
      ) : data?.status === 'active' && data.stats ? (
        <Dashboard a={data as Affiliate & { stats: Stats }} />
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
