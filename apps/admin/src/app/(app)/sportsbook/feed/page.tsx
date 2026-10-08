'use client';

import Link from 'next/link';
import { useState } from 'react';
import {
  BsArrowRepeat, BsBroadcast, BsCheckCircleFill, BsClock, BsEye, BsEyeSlash, BsKey, BsLightningCharge, BsLink45Deg,
  BsPlayFill, BsShieldCheck, BsXCircleFill,
} from 'react-icons/bs';
import {
  Badge, Btn, Field, Notice, PageHeader, Panel, StatTile, TextInput, cx,
} from '@/components/console/ui';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';
import { LoadingState } from '@slyk/ui/components/spinner';

interface Feed {
  provider: string;
  has_key: boolean;
  key_hint: string;
  key_source: 'console' | 'environment' | 'none';
  base_url: string;
  base_url_source: 'console' | 'environment';
  live_betting: boolean;
  live_odds_interval: number | null;
  live_odds_stale: number | null;
  live_bet_delay: number | null;
  counts: {
    feed_events: number; manual_events: number; upcoming: number; awaiting_odds: number; live: number;
    locked: number; leagues_enabled: number; leagues_total: number; markets_to_review: number;
  };
  last_live_odds_at: string | null;
  schedules: { task: string; label: string; enabled: boolean; last_run_at: string | null; every: string }[];
  jobs: { id: string; label: string }[];
}

interface TestResult {
  ok: boolean; error?: string; account?: string; email?: string; plan?: string; active?: boolean; ends?: string | null;
  requests_today?: number | null; requests_limit?: number | null;
}

const JOB_HELP: Record<string, string> = {
  import_fixtures: 'Pull new upcoming fixtures from every enabled league.',
  sync_odds: 'Refresh 1X2 and market prices for upcoming matches.',
  sync_live: 'Update scores and statuses for matches in play.',
  sync_live_odds: 'Refresh in-play prices and confirm pending in-play bets.',
  settle_finished: 'Settle matches that finished in the last few days.',
};

function ago(iso: string | null) {
  if (!iso) return 'never';
  const s = Math.max(0, (Date.now() - new Date(iso).getTime()) / 1000);
  if (s < 60) return `${Math.round(s)}s ago`;
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  return new Date(iso).toLocaleString();
}

export default function FeedPage() {
  const { accessToken } = useAuth();
  const { data: feed, loading, refetch } = useApi<Feed>('/admin/sportsbook/feed/');
  const [key, setKey] = useState('');
  const [showKey, setShowKey] = useState(false);
  const [baseUrl, setBaseUrl] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [test, setTest] = useState<TestResult | null>(null);
  const [running, setRunning] = useState<string | null>(null);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red' | 'indigo'; text: string } | null>(null);

  if (loading && !feed) return <LoadingState className="py-24" label="Loading feed settings…" />;
  if (!feed) return <Notice tone="red">Couldn&apos;t load the feed settings.</Notice>;

  const url = baseUrl ?? feed.base_url;
  const dirty = key.trim() !== '' || url !== feed.base_url;

  async function save(body: Record<string, unknown>, text: string) {
    if (!accessToken) return;
    setSaving(true);
    const res = await authedRequest<Feed>('PUT', '/admin/sportsbook/feed/', accessToken, body);
    setSaving(false);
    if (res.error) { setNotice({ tone: 'red', text: res.error }); return; }
    setKey(''); setBaseUrl(null); setTest(null);
    setNotice({ tone: 'green', text });
    refetch();
  }

  async function runTest() {
    if (!accessToken) return;
    setTesting(true);
    const res = await authedRequest<TestResult>('POST', '/admin/sportsbook/feed/test/', accessToken);
    setTesting(false);
    setTest(res.data ?? { ok: false, error: res.error });
  }

  async function runJob(id: string, label: string) {
    if (!accessToken) return;
    setRunning(id);
    const res = await authedRequest('POST', '/admin/sportsbook/feed/sync/', accessToken, { job: id });
    setRunning(null);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'indigo', text: `${label} started. Results appear on the Matches page in a minute or two.` });
    setTimeout(refetch, 4000);
  }

  const c = feed.counts;
  const quota = test?.ok && test.requests_limit ? Math.min(100, ((test.requests_today ?? 0) / test.requests_limit) * 100) : null;
  const schedule = (task: string) => feed.schedules.find((s) => s.task.endsWith(task));

  return (
    <div className="space-y-6">
      <PageHeader
        icon={BsBroadcast}
        eyebrow="Sportsbook"
        title="Odds feed"
        description="The api-football connection that imports fixtures, prices, live scores and results."
        actions={feed.has_key
          ? <Badge tone="green" dot>Connected · key {feed.key_hint}</Badge>
          : <Badge tone="red" dot>No API key</Badge>}
      />

      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}

      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <StatTile icon={BsBroadcast} tone="red" label="Live now" value={c.live} href="/sportsbook/matches?state=live" />
        <StatTile icon={BsCheckCircleFill} tone="green" label="Upcoming, priced" value={c.upcoming} href="/sportsbook/matches" hint={`${c.feed_events.toLocaleString()} from feed · ${c.manual_events} manual`} />
        <StatTile icon={BsClock} tone="gold" label="Awaiting odds" value={c.awaiting_odds} href="/sportsbook/matches?state=unpriced" />
        <StatTile icon={BsShieldCheck} tone="indigo" label="Leagues enabled" value={`${c.leagues_enabled}/${c.leagues_total}`} href="/sportsbook/leagues" />
      </div>

      <div className="grid gap-6 xl:grid-cols-[1.25fr_1fr]">
        <Panel
          title={<span className="flex items-center gap-2"><BsKey size={14} />API connection</span>}
          description={feed.key_source === 'environment'
            ? 'Using the key from the server environment (.env.prod). Saving one here overrides it.'
            : 'Your api-football key from dashboard.api-football.com. Stored on the server; only the last four characters are ever shown.'}
        >
          <div className="space-y-4">
            <Field label="API key" hint={feed.has_key ? `Current key ends ${feed.key_hint} (${feed.key_source === 'console' ? 'set here' : 'from environment'}). Leave empty to keep it.` : 'No key yet — the feed is switched off until you add one.'}>
              <div className="relative">
                <TextInput
                  type={showKey ? 'text' : 'password'}
                  autoComplete="off"
                  value={key}
                  onChange={(e) => setKey(e.target.value)}
                  placeholder={feed.has_key ? '•••••••••••••••• (unchanged)' : 'Paste your api-football key'}
                  className="pr-10 font-mono"
                />
                <button type="button" onClick={() => setShowKey((v) => !v)} aria-label={showKey ? 'Hide key' : 'Show key'} className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-foreground">
                  {showKey ? <BsEyeSlash size={14} /> : <BsEye size={14} />}
                </button>
              </div>
            </Field>
            <Field label="API base URL" hint="Leave as is unless api-football tells you otherwise (RapidAPI keys use a different host).">
              <div className="relative">
                <BsLink45Deg className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={14} />
                <TextInput value={url} onChange={(e) => setBaseUrl(e.target.value)} className="pl-9 font-mono text-[13px]" />
              </div>
            </Field>
            <div className="flex flex-wrap gap-2">
              <Btn variant="primary" busy={saving} disabled={!dirty} onClick={() => save({ api_key: key.trim(), base_url: url }, 'Feed settings saved.')}>Save connection</Btn>
              <Btn icon={BsLightningCharge} busy={testing} disabled={!feed.has_key || dirty} onClick={runTest}>Test connection</Btn>
              {feed.key_source === 'console' && (
                <Btn variant="danger" onClick={() => { if (confirm('Remove the key saved here? The environment key (if any) will be used instead.')) void save({ clear_key: true }, 'Key removed.'); }}>Remove key</Btn>
              )}
            </div>
            {dirty && feed.has_key && <p className="text-xs text-muted-foreground">Save first, then test the new settings.</p>}

            {test && (
              <div className={cx('rounded-2xl border p-4', test.ok ? 'border-win/30 bg-win/5' : 'border-live/30 bg-live/5')}>
                {test.ok ? (
                  <div className="space-y-3">
                    <p className="flex items-center gap-2 font-semibold text-win"><BsCheckCircleFill /> Connected to api-football</p>
                    <dl className="grid grid-cols-2 gap-3 text-sm">
                      <div><dt className="text-xs text-muted-foreground">Account</dt><dd className="font-semibold">{test.account || test.email || '—'}</dd></div>
                      <div><dt className="text-xs text-muted-foreground">Plan</dt><dd className="font-semibold">{test.plan || '—'} {test.active === false && <Badge tone="red">inactive</Badge>}</dd></div>
                      <div><dt className="text-xs text-muted-foreground">Renews</dt><dd className="font-semibold">{test.ends ? new Date(test.ends).toLocaleDateString() : '—'}</dd></div>
                      <div><dt className="text-xs text-muted-foreground">Requests today</dt><dd className="font-semibold tabular-nums">{test.requests_today?.toLocaleString() ?? '—'} / {test.requests_limit?.toLocaleString() ?? '—'}</dd></div>
                    </dl>
                    {quota != null && (
                      <div>
                        <div className="h-2 overflow-hidden rounded-full bg-muted">
                          <div className={cx('h-full rounded-full', quota > 85 ? 'bg-live' : quota > 60 ? 'bg-gold' : 'bg-win')} style={{ width: `${quota}%` }} />
                        </div>
                        <p className="mt-1 text-xs text-muted-foreground">{quota.toFixed(0)}% of today&apos;s quota used.</p>
                      </div>
                    )}
                  </div>
                ) : (
                  <p className="flex items-start gap-2 text-sm font-semibold text-live"><BsXCircleFill className="mt-0.5 shrink-0" /> {test.error}</p>
                )}
              </div>
            )}
          </div>
        </Panel>

        <Panel title={<span className="flex items-center gap-2"><BsLightningCharge size={14} />In-play betting</span>} description="Set in the server environment (.env.prod); shown here for reference.">
          <dl className="divide-y divide-border/60 text-sm">
            {[
              ['Live betting', feed.live_betting ? <Badge tone="green" dot>On</Badge> : <Badge tone="slate">Off</Badge>],
              ['Live odds refresh', feed.live_odds_interval ? `every ${feed.live_odds_interval}s` : '—'],
              ['Suspend when prices are older than', feed.live_odds_stale ? `${feed.live_odds_stale}s` : '—'],
              ['In-play bet delay', feed.live_bet_delay ? `${feed.live_bet_delay}s` : '—'],
              ['Last live price received', ago(feed.last_live_odds_at)],
              ['Matches with manual prices', <Link key="l" href="/sportsbook/matches?state=locked" className="font-semibold text-secondary hover:underline">{c.locked}</Link>],
              ['Markets waiting for review', c.markets_to_review],
            ].map(([k, v]) => (
              <div key={String(k)} className="flex items-center justify-between gap-4 py-2.5">
                <dt className="text-muted-foreground">{k}</dt>
                <dd className="text-right font-semibold">{v}</dd>
              </div>
            ))}
          </dl>
        </Panel>
      </div>

      <Panel
        title={<span className="flex items-center gap-2"><BsArrowRepeat size={14} />Feed jobs</span>}
        description="These run automatically on a schedule. Run one now after changing the key or enabling leagues."
        padded={false}
      >
        <div className="divide-y divide-border/60">
          {feed.jobs.map((j) => {
            const s = schedule(j.id === 'import_fixtures' ? 'import_upcoming_fixtures' : j.id === 'sync_odds' ? 'sync_fixture_odds'
              : j.id === 'sync_live' ? 'sync_live_fixtures' : j.id === 'sync_live_odds' ? 'sync_live_odds' : 'settle_finished_fixtures');
            return (
              <div key={j.id} className="flex flex-wrap items-center gap-4 px-5 py-4">
                <div className="min-w-0 flex-1">
                  <p className="font-semibold">{j.label}</p>
                  <p className="text-xs text-muted-foreground">{JOB_HELP[j.id]}</p>
                </div>
                <div className="text-right text-xs text-muted-foreground">
                  {s ? (
                    <>
                      <p>{s.enabled ? s.every || 'scheduled' : 'schedule off'}</p>
                      <p>Last run {ago(s.last_run_at)}</p>
                    </>
                  ) : <p>Not scheduled</p>}
                </div>
                <Btn size="sm" icon={BsPlayFill} busy={running === j.id} disabled={!feed.has_key} onClick={() => runJob(j.id, j.label)}>Run now</Btn>
              </div>
            );
          })}
        </div>
      </Panel>
    </div>
  );
}
