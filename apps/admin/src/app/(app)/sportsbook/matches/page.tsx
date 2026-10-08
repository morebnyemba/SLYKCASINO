'use client';

import Link from 'next/link';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { Suspense, useEffect, useState } from 'react';
import { BsCalendar2Week, BsChevronRight, BsPlusLg, BsSearch, BsStar, BsStarFill } from 'react-icons/bs';
import {
  Btn, Drawer, EmptyState, Field, Notice, PageHeader, Pager, Panel, Select, Switch, Tabs, TextInput,
  cx, inputClass, tableClass, tdClass, thClass, trClass,
} from '@/components/console/ui';
import { LeaguePicker } from '@/components/sportsbook/league-picker';
import { MatchCell, OddsTrio, SourceBadge, StateBadge } from '@/components/sportsbook/match-bits';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';
import { SPORTS, fromLocalInput, kickoff, type AdminMatch, type LeagueRef, type Paged } from '@/lib/sportsbook';
import { LoadingState } from '@slyk/ui/components/spinner';

type StateFilter = 'upcoming' | 'live' | 'unpriced' | 'closed' | 'finished' | 'locked' | 'all';
const PAGE_SIZE = 50;

interface Summary { upcoming: number; live: number; unpriced: number; closed: number; finished: number; locked: number }

const BLANK = {
  home: '', away: '', sport: 'football', starts_at: '', odds: '', odds_draw: '', odds_away: '',
  featured: false, is_open: true,
};

function NewMatchDrawer({ open, onClose, onCreated }: { open: boolean; onClose: () => void; onCreated: (id: number) => void }) {
  const { accessToken } = useAuth();
  const [form, setForm] = useState({ ...BLANK });
  const [league, setLeague] = useState<LeagueRef | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const set = <K extends keyof typeof BLANK>(k: K, v: (typeof BLANK)[K]) => setForm((f) => ({ ...f, [k]: v }));

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!accessToken) return;
    setBusy(true); setError('');
    const res = await authedRequest<AdminMatch>('POST', '/admin/sportsbook/events/', accessToken, {
      home_team_name: form.home, away_team_name: form.away, sport: form.sport,
      starts_at: fromLocalInput(form.starts_at), league: league?.id ?? null,
      odds: form.odds || '1.00', odds_draw: form.odds_draw || null, odds_away: form.odds_away || null,
      has_odds: !!form.odds, featured: form.featured, is_open: form.is_open,
    });
    setBusy(false);
    if (res.error || !res.data) { setError(res.error ?? 'Could not create the match.'); return; }
    setForm({ ...BLANK }); setLeague(null);
    onCreated(res.data.id);
  }

  return (
    <Drawer
      open={open}
      onClose={onClose}
      title="New match"
      description="Add a match the feed doesn't cover. Players see it as soon as it has prices and is open."
      footer={(
        <>
          <Btn onClick={onClose}>Cancel</Btn>
          <Btn variant="primary" type="submit" form="new-match" busy={busy} icon={BsPlusLg}>Create match</Btn>
        </>
      )}
    >
      <form id="new-match" onSubmit={submit} className="space-y-5">
        <div className="grid grid-cols-2 gap-3">
          <Field label="Home team"><TextInput required value={form.home} onChange={(e) => set('home', e.target.value)} placeholder="Dynamos" /></Field>
          <Field label="Away team"><TextInput required value={form.away} onChange={(e) => set('away', e.target.value)} placeholder="CAPS United" /></Field>
        </div>
        <Field label="League"><LeaguePicker value={league} onChange={setLeague} /></Field>
        <div className="grid grid-cols-2 gap-3">
          <Field label="Kick-off"><TextInput required type="datetime-local" value={form.starts_at} onChange={(e) => set('starts_at', e.target.value)} /></Field>
          <Field label="Sport">
            <Select value={form.sport} onChange={(e) => set('sport', e.target.value)}>
              {SPORTS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
            </Select>
          </Field>
        </div>
        <div>
          <p className="mb-1.5 text-[12.5px] font-semibold text-muted-foreground">Match result prices (leave empty to add later)</p>
          <div className="grid grid-cols-3 gap-3">
            {([['odds', '1 · Home'], ['odds_draw', 'X · Draw'], ['odds_away', '2 · Away']] as const).map(([k, label]) => (
              <Field key={k} label={label}>
                <TextInput type="number" step="0.01" min="1" value={form[k]} onChange={(e) => set(k, e.target.value)} placeholder="0.00" />
              </Field>
            ))}
          </div>
        </div>
        <div className="space-y-3 rounded-xl border border-border/70 p-4">
          <label className="flex items-center justify-between gap-3 text-sm">
            <span><span className="font-semibold">Open for betting</span><span className="block text-xs text-muted-foreground">Players can place bets until kick-off.</span></span>
            <Switch checked={form.is_open} onChange={(v) => set('is_open', v)} label="Open for betting" />
          </label>
          <label className="flex items-center justify-between gap-3 text-sm">
            <span><span className="font-semibold">Featured</span><span className="block text-xs text-muted-foreground">Shown in Top matches.</span></span>
            <Switch checked={form.featured} onChange={(v) => set('featured', v)} label="Featured" />
          </label>
        </div>
        {error && <Notice tone="red">{error}</Notice>}
      </form>
    </Drawer>
  );
}

function MatchesScreen() {
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const { accessToken } = useAuth();

  const state = (params.get('state') as StateFilter) || 'upcoming';
  const source = params.get('source') ?? '';
  const [search, setSearch] = useState(params.get('q') ?? '');
  const [q, setQ] = useState(params.get('q') ?? '');
  const [page, setPage] = useState(1);
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);

  useEffect(() => { const t = setTimeout(() => setQ(search.trim()), 300); return () => clearTimeout(t); }, [search]);
  useEffect(() => { setPage(1); }, [state, source, q]);

  function setParam(key: string, value: string) {
    const next = new URLSearchParams(params.toString());
    if (value) next.set(key, value); else next.delete(key);
    router.replace(`${pathname}?${next.toString()}`, { scroll: false });
  }

  const query = new URLSearchParams({ page: String(page), page_size: String(PAGE_SIZE) });
  if (state !== 'all') query.set('state', state);
  if (source) query.set('source', source);
  if (q) query.set('q', q);
  const { data, loading, refetch } = useApi<Paged<AdminMatch>>(`/admin/sportsbook/events/?${query}`);
  const { data: summary, refetch: refetchSummary } = useApi<Summary>('/admin/sportsbook/events/summary/');
  const rows = data?.results ?? [];

  async function patch(m: AdminMatch, body: Partial<AdminMatch>, label: string) {
    if (!accessToken) return;
    const res = await authedRequest('PATCH', `/admin/sportsbook/events/${m.id}/`, accessToken, body);
    setNotice(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: `${m.name}: ${label}.` });
    refetch(); refetchSummary();
  }

  const tabs: { id: StateFilter; label: string; count?: number; tone?: 'red' }[] = [
    { id: 'upcoming', label: 'Upcoming', count: summary?.upcoming },
    { id: 'live', label: 'Live', count: summary?.live, tone: summary?.live ? 'red' : undefined },
    { id: 'unpriced', label: 'Awaiting odds', count: summary?.unpriced },
    { id: 'closed', label: 'Suspended', count: summary?.closed },
    { id: 'locked', label: 'Manual prices', count: summary?.locked },
    { id: 'finished', label: 'Finished', count: summary?.finished },
    { id: 'all', label: 'All' },
  ];

  return (
    <div className="space-y-5">
      <PageHeader
        icon={BsCalendar2Week}
        eyebrow="Sportsbook"
        title="Matches"
        description="Every match players can bet on: from the odds feed or added by hand. Open one to edit prices, scores or settle it."
        actions={<Btn variant="primary" icon={BsPlusLg} onClick={() => setCreating(true)}>New match</Btn>}
      />

      <div className="flex flex-col gap-3 2xl:flex-row 2xl:items-center">
        <Tabs value={state} onChange={(v) => setParam('state', v === 'upcoming' ? '' : v)} items={tabs} />
        <div className="flex flex-1 gap-2 2xl:justify-end">
          <div className="relative min-w-0 flex-1 sm:max-w-sm">
            <BsSearch className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" size={13} />
            <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Team, match or feed id" className={cx(inputClass, 'pl-9')} />
          </div>
          <div className="w-44 shrink-0">
            <Select value={source} onChange={(e) => setParam('source', e.target.value)}>
              <option value="">All sources</option>
              <option value="feed">From feed</option>
              <option value="manual">Added by hand</option>
            </Select>
          </div>
        </div>
      </div>

      {notice && <Notice tone={notice.tone} onClose={() => setNotice(null)}>{notice.text}</Notice>}

      <Panel padded={false}>
        {loading && !data ? (
          <LoadingState className="py-16" label="Loading matches…" />
        ) : rows.length === 0 ? (
          <EmptyState icon={BsCalendar2Week} title="No matches here" action={<Btn icon={BsPlusLg} onClick={() => setCreating(true)}>New match</Btn>}>
            {q ? 'Nothing matches that search.' : 'Matches appear here as the odds feed imports them, or when you add one.'}
          </EmptyState>
        ) : (
          <>
          {/* Phones: one card per match. */}
          <div className="divide-y divide-border/60 sm:hidden">
            {rows.map((m) => (
              <Link key={m.id} href={`/sportsbook/matches/${m.id}`} className="block space-y-2.5 p-4 active:bg-muted/40">
                <div className="flex items-center justify-between gap-2">
                  <span className="text-xs font-semibold text-muted-foreground">{kickoff(m.starts_at)}</span>
                  <StateBadge m={m} />
                </div>
                <MatchCell m={m} />
                <div className="flex items-center justify-between gap-2">
                  <OddsTrio m={m} />
                  <BsChevronRight className="text-muted-foreground" size={13} />
                </div>
              </Link>
            ))}
          </div>
          <div className="hidden overflow-x-auto sm:block">
            <table className={tableClass}>
              <thead>
                <tr>
                  <th className={thClass}>Kick-off</th>
                  <th className={thClass}>Match</th>
                  <th className={thClass}>State</th>
                  <th className={thClass}>1 · X · 2</th>
                  <th className={cx(thClass, 'text-center')}>Bets</th>
                  <th className={cx(thClass, 'text-center')}>Open</th>
                  <th className={cx(thClass, 'text-center')}>Top</th>
                  <th className={thClass} />
                </tr>
              </thead>
              <tbody>
                {rows.map((m) => (
                  <tr key={m.id} className={trClass}>
                    <td className={cx(tdClass, 'whitespace-nowrap')}>
                      <p className="text-[13px] font-semibold">{kickoff(m.starts_at)}</p>
                      <div className="mt-1"><SourceBadge m={m} /></div>
                    </td>
                    <td className={tdClass}>
                      <Link href={`/sportsbook/matches/${m.id}`} className="block hover:opacity-90"><MatchCell m={m} /></Link>
                    </td>
                    <td className={tdClass}><StateBadge m={m} /></td>
                    <td className={tdClass}><OddsTrio m={m} /></td>
                    <td className={cx(tdClass, 'text-center font-mono text-[13px] tabular-nums')}>{m.bets_count || '—'}</td>
                    <td className={cx(tdClass, 'text-center')}>
                      <Switch
                        checked={m.is_open}
                        onChange={(v) => patch(m, { is_open: v }, v ? 'opened for betting' : 'suspended')}
                        label={`${m.name} open for betting`}
                        disabled={m.state === 'finished' || m.state === 'void'}
                      />
                    </td>
                    <td className={cx(tdClass, 'text-center')}>
                      <button
                        onClick={() => patch(m, { featured: !m.featured }, m.featured ? 'removed from Top matches' : 'added to Top matches')}
                        aria-label={m.featured ? 'Remove from Top matches' : 'Add to Top matches'}
                        className={cx('rounded-lg p-2 transition-colors hover:bg-muted', m.featured ? 'text-gold' : 'text-muted-foreground/50')}
                      >
                        {m.featured ? <BsStarFill size={14} /> : <BsStar size={14} />}
                      </button>
                    </td>
                    <td className={cx(tdClass, 'text-right')}>
                      <Link href={`/sportsbook/matches/${m.id}`} className="inline-flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-semibold text-secondary hover:bg-secondary/10">
                        Manage <BsChevronRight size={11} />
                      </Link>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          </>
        )}
        <Pager page={page} count={data?.count ?? 0} pageSize={PAGE_SIZE} onPage={setPage} />
      </Panel>

      <NewMatchDrawer
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={(id) => { setCreating(false); router.push(`/sportsbook/matches/${id}`); }}
      />
    </div>
  );
}

export default function MatchesPage() {
  return (
    <Suspense fallback={<LoadingState className="py-16" />}>
      <MatchesScreen />
    </Suspense>
  );
}
