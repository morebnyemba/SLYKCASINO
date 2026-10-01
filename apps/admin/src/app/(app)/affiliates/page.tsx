'use client';

import { Fragment, useState } from 'react';
import { FaHandshake } from 'react-icons/fa';
import { Card, CardContent } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { useAuth } from '@/lib/auth-context';
import { authedPost, useApi } from '@/lib/use-api';

interface Affiliate {
  id: number;
  player_id: number;
  username: string;
  code: string;
  status: 'pending' | 'active' | 'suspended' | 'rejected';
  revshare_percent: string;
  cpa_amount: string;
  cpa_min_deposit: string;
  website: string;
  note: string;
  referrals_count: number;
  clicks_count: number;
  created_at: string;
}

interface Commission {
  id: number;
  affiliate_code: string;
  kind: 'revshare' | 'cpa';
  period: string | null;
  base_amount: string;
  rate: string;
  amount: string;
  active_players: number;
  status: 'pending' | 'approved' | 'paid' | 'rejected';
  note: string;
  created_at: string;
}

type Page<T> = { results?: T[] } | T[];
const rowsOf = <T,>(d?: Page<T> | null) => (Array.isArray(d) ? d : d?.results ?? []);

const money = (v: string) => `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;

const AFFILIATE_BADGE: Record<Affiliate['status'], 'success' | 'secondary' | 'destructive'> = {
  active: 'success', pending: 'secondary', suspended: 'destructive', rejected: 'destructive',
};
const COMMISSION_BADGE: Record<Commission['status'], 'success' | 'secondary' | 'destructive'> = {
  paid: 'success', pending: 'secondary', approved: 'secondary', rejected: 'destructive',
};

function Filter({ value, onChange, options }: { value: string; onChange: (v: string) => void; options: [string, string][] }) {
  return (
    <div className="flex w-fit gap-1 rounded-md bg-muted p-1">
      {options.map(([id, label]) => (
        <button
          key={id}
          onClick={() => onChange(id)}
          className={`rounded-md px-3 py-1.5 text-xs font-medium transition-colors ${
            value === id ? 'bg-background text-foreground shadow-sm' : 'text-muted-foreground hover:text-foreground'
          }`}
        >
          {label}
        </button>
      ))}
    </div>
  );
}

function TermsEditor({ a, onSaved }: { a: Affiliate; onSaved: () => void }) {
  const { accessToken } = useAuth();
  const [form, setForm] = useState({
    code: a.code, revshare_percent: a.revshare_percent, cpa_amount: a.cpa_amount,
    cpa_min_deposit: a.cpa_min_deposit, note: a.note,
  });
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);

  async function save() {
    if (!accessToken) return;
    setBusy(true); setError('');
    const res = await authedPost(`/admin/affiliates/${a.id}/terms/`, form, accessToken);
    setBusy(false);
    if (res.error) setError(res.error); else onSaved();
  }

  const field = (key: keyof typeof form, label: string, width = 'w-28') => (
    <label className="space-y-1 text-xs">
      <span className="text-muted-foreground">{label}</span>
      <input
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
        className={`block ${width} rounded-md border border-border bg-background px-2 py-1.5 text-sm`}
      />
    </label>
  );

  return (
    <div className="space-y-3 bg-muted/40 px-4 py-4">
      <div className="flex flex-wrap items-end gap-3">
        {field('code', 'Code', 'w-36')}
        {field('revshare_percent', 'Revenue share %')}
        {field('cpa_amount', 'CPA amount')}
        {field('cpa_min_deposit', 'CPA min. deposit')}
        {field('note', 'Internal note', 'w-64')}
        <button onClick={save} disabled={busy} className="rounded-md bg-gold px-3 py-1.5 text-xs font-bold text-gold-foreground disabled:opacity-60">
          {busy ? 'Saving…' : 'Save terms'}
        </button>
      </div>
      {a.website && <p className="text-xs text-muted-foreground">Promotes on: {a.website}</p>}
      {error && <p className="text-xs text-red-500">{error}</p>}
    </div>
  );
}

function AffiliatesTab() {
  const { accessToken } = useAuth();
  const [status, setStatus] = useState('pending');
  const { data, loading, refetch } = useApi<Page<Affiliate>>(`/admin/affiliates/?status=${status}&page_size=100`);
  const [open, setOpen] = useState<number | null>(null);
  const [error, setError] = useState('');
  const rows = rowsOf(data);

  async function setAffiliateStatus(id: number, next: Affiliate['status']) {
    if (!accessToken) return;
    setError('');
    const res = await authedPost(`/admin/affiliates/${id}/status/`, { status: next }, accessToken);
    if (res.error) setError(res.error);
    refetch();
  }

  const action = (label: string, onClick: () => void, tone = 'text-foreground') => (
    <button onClick={onClick} className={`rounded-md border border-border px-2 py-1 text-xs font-medium hover:bg-muted ${tone}`}>{label}</button>
  );

  return (
    <div className="space-y-4">
      <Filter value={status} onChange={setStatus} options={[['pending', 'Pending'], ['active', 'Active'], ['suspended', 'Suspended'], ['rejected', 'Rejected'], ['', 'All']]} />
      {error && <p className="text-sm text-red-500">{error}</p>}
      <Card>
        <CardContent className="p-0">
          {loading && <p className="p-4 text-sm text-muted-foreground">Loading affiliates…</p>}
          {!loading && rows.length === 0 && <p className="p-4 text-sm text-muted-foreground">No affiliates for this filter.</p>}
          {rows.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Affiliate</th>
                  <th className="px-4 py-3 font-medium">Code</th>
                  <th className="px-4 py-3 font-medium">Terms</th>
                  <th className="px-4 py-3 font-medium">Clicks / sign-ups</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((a) => (
                  <Fragment key={a.id}>
                    <tr className="border-b border-border align-top">
                      <td className="px-4 py-3">
                        <p className="font-medium">{a.username || `#${a.player_id}`}</p>
                        <p className="text-xs text-muted-foreground">Applied {new Date(a.created_at).toLocaleDateString()}</p>
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">{a.code}</td>
                      <td className="px-4 py-3 text-xs">
                        {Number(a.revshare_percent)}% rev share
                        {Number(a.cpa_amount) > 0 && <><br />{money(a.cpa_amount)} CPA ≥ {money(a.cpa_min_deposit)}</>}
                      </td>
                      <td className="px-4 py-3 tabular-nums">{a.clicks_count} / {a.referrals_count}</td>
                      <td className="px-4 py-3"><Badge variant={AFFILIATE_BADGE[a.status]}>{a.status}</Badge></td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap gap-1.5">
                          {a.status === 'pending' && action('Approve', () => setAffiliateStatus(a.id, 'active'), 'text-green-500')}
                          {a.status === 'pending' && action('Reject', () => setAffiliateStatus(a.id, 'rejected'), 'text-red-500')}
                          {a.status === 'active' && action('Suspend', () => setAffiliateStatus(a.id, 'suspended'), 'text-red-500')}
                          {(a.status === 'suspended' || a.status === 'rejected') && action('Activate', () => setAffiliateStatus(a.id, 'active'))}
                          {action(open === a.id ? 'Close' : 'Terms', () => setOpen(open === a.id ? null : a.id))}
                        </div>
                      </td>
                    </tr>
                    {open === a.id && (
                      <tr className="border-b border-border">
                        <td colSpan={6} className="p-0"><TermsEditor a={a} onSaved={() => { setOpen(null); refetch(); }} /></td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function CommissionsTab() {
  const { accessToken } = useAuth();
  const [status, setStatus] = useState('pending');
  const { data, loading, refetch } = useApi<Page<Commission>>(`/admin/affiliate-commissions/?status=${status}`);
  const [message, setMessage] = useState('');
  const [busy, setBusy] = useState<number | 'run' | null>(null);
  const rows = rowsOf(data);

  async function act(id: number, verb: 'approve' | 'reject') {
    if (!accessToken) return;
    if (verb === 'approve' && !window.confirm('Pay this commission into the affiliate’s wallet?')) return;
    setBusy(id); setMessage('');
    const res = await authedPost(`/admin/affiliate-commissions/${id}/${verb}/`, {}, accessToken);
    setBusy(null);
    setMessage(res.error ? `Error: ${res.error}` : verb === 'approve' ? 'Commission paid.' : 'Commission rejected.');
    refetch();
  }

  async function runNow() {
    if (!accessToken) return;
    setBusy('run'); setMessage('');
    const res = await authedPost<{ period: string; revshare: number; cpa: number }>('/admin/affiliate-commissions/run/', {}, accessToken);
    setBusy(null);
    setMessage(res.error ? `Error: ${res.error}` : `Calculated ${res.data?.period?.slice(0, 7)}: ${res.data?.revshare} revenue share, ${res.data?.cpa} new CPA.`);
    refetch();
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center gap-3">
        <Filter value={status} onChange={setStatus} options={[['pending', 'To review'], ['paid', 'Paid'], ['rejected', 'Rejected'], ['', 'All']]} />
        <button
          onClick={runNow}
          disabled={busy === 'run'}
          title="Closes last month's revenue share and picks up new CPAs. Also runs automatically every 6 hours; safe to repeat."
          className="ml-auto rounded-md border border-border px-3 py-1.5 text-xs font-medium hover:bg-muted disabled:opacity-60"
        >
          {busy === 'run' ? 'Calculating…' : 'Calculate now'}
        </button>
      </div>
      {message && <p className={`text-sm ${message.startsWith('Error') ? 'text-red-500' : 'text-muted-foreground'}`}>{message}</p>}
      <Card>
        <CardContent className="p-0">
          {loading && <p className="p-4 text-sm text-muted-foreground">Loading commissions…</p>}
          {!loading && rows.length === 0 && <p className="p-4 text-sm text-muted-foreground">No commissions for this filter.</p>}
          {rows.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Affiliate</th>
                  <th className="px-4 py-3 font-medium">For</th>
                  <th className="px-4 py-3 font-medium">Calculation</th>
                  <th className="px-4 py-3 text-right font-medium">Amount</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((c) => (
                  <tr key={c.id} className="border-b border-border last:border-0">
                    <td className="px-4 py-3 font-mono text-xs">{c.affiliate_code}</td>
                    <td className="px-4 py-3">{c.kind === 'cpa' ? 'CPA' : c.period?.slice(0, 7)}</td>
                    <td className="px-4 py-3 text-xs text-muted-foreground">
                      {c.kind === 'cpa'
                        ? `Referral deposited ${money(c.base_amount)}`
                        : `${money(c.base_amount)} NGR × ${Number(c.rate)}% (${c.active_players} active)`}
                    </td>
                    <td className="px-4 py-3 text-right font-semibold tabular-nums">{money(c.amount)}</td>
                    <td className="px-4 py-3"><Badge variant={COMMISSION_BADGE[c.status]}>{c.status}</Badge></td>
                    <td className="px-4 py-3">
                      {c.status === 'pending' || c.status === 'approved' ? (
                        <div className="flex gap-1.5">
                          <button disabled={busy === c.id} onClick={() => act(c.id, 'approve')} className="rounded-md bg-gold px-2 py-1 text-xs font-bold text-gold-foreground disabled:opacity-60">Approve &amp; pay</button>
                          {c.status === 'pending' && (
                            <button disabled={busy === c.id} onClick={() => act(c.id, 'reject')} className="rounded-md border border-border px-2 py-1 text-xs font-medium text-red-500 hover:bg-muted">Reject</button>
                          )}
                        </div>
                      ) : '—'}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

export default function AffiliatesPage() {
  const [tab, setTab] = useState<'affiliates' | 'commissions'>('affiliates');
  return (
    <div className="space-y-6">
      <div className="flex items-center gap-2.5">
        <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gold/15 text-gold"><FaHandshake size={15} /></span>
        <div>
          <h1 className="text-2xl font-bold">Affiliates</h1>
          <p className="text-sm text-muted-foreground">Approve partners, set their terms, and review and pay commissions.</p>
        </div>
      </div>
      <Filter value={tab} onChange={(v) => setTab(v as typeof tab)} options={[['affiliates', 'Affiliates'], ['commissions', 'Commissions']]} />
      {tab === 'affiliates' ? <AffiliatesTab /> : <CommissionsTab />}
    </div>
  );
}
