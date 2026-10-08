'use client';

import Link from 'next/link';
import { useParams, useRouter } from 'next/navigation';
import { useEffect, useState } from 'react';
import {
  BsArrowLeft, BsBroadcast, BsCalendar2Week, BsCash, BsInfoCircle, BsLockFill, BsSave, BsTrash3, BsUnlock,
} from 'react-icons/bs';
import {
  Badge, Btn, EmptyState, Field, Notice, Panel, Select, Switch, TextInput, cx,
} from '@/components/console/ui';
import { LeaguePicker } from '@/components/sportsbook/league-picker';
import { LeagueTag, SourceBadge, StateBadge, TeamCrest } from '@/components/sportsbook/match-bits';
import { SettlePanel, type MarketRow } from '@/components/sportsbook/settle-panel';
import { useAuth } from '@/lib/auth-context';
import { authedRequest, useApi } from '@/lib/use-api';
import {
  SPORTS, STATUSES, fromLocalInput, kickoff, teamNames, toLocalInput, type AdminMatch, type LeagueRef,
} from '@/lib/sportsbook';
import { LoadingState } from '@slyk/ui/components/spinner';

type Msg = { tone: 'green' | 'red'; text: string } | null;

function SaveBar({ busy, dirty, msg, onSave, onReset }: {
  busy: boolean; dirty: boolean; msg: Msg; onSave: () => void; onReset: () => void;
}) {
  return (
    <div className="mt-5 flex flex-wrap items-center gap-2 border-t border-border/60 pt-4">
      <Btn variant="primary" icon={BsSave} busy={busy} disabled={!dirty} onClick={onSave}>Save changes</Btn>
      {dirty && <Btn variant="ghost" onClick={onReset}>Discard</Btn>}
      {msg && <span className={cx('text-sm font-medium', msg.tone === 'green' ? 'text-win' : 'text-live')}>{msg.text}</span>}
    </div>
  );
}

/** One editable section: keeps its own draft and saves only its fields. */
function useSection<T extends Record<string, unknown>>(initial: T, match: AdminMatch | null, onSaved: (m: AdminMatch) => void) {
  const { accessToken } = useAuth();
  const [draft, setDraft] = useState<T>(initial);
  const [base, setBase] = useState<T>(initial);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<Msg>(null);
  useEffect(() => { setDraft(initial); setBase(initial); /* eslint-disable-next-line react-hooks/exhaustive-deps */ }, [JSON.stringify(initial)]);
  const dirty = JSON.stringify(draft) !== JSON.stringify(base);
  async function save(body: Record<string, unknown>) {
    if (!accessToken || !match) return;
    setBusy(true); setMsg(null);
    const res = await authedRequest<AdminMatch>('PATCH', `/admin/sportsbook/events/${match.id}/`, accessToken, body);
    setBusy(false);
    if (res.error || !res.data) { setMsg({ tone: 'red', text: res.error ?? 'Could not save.' }); return; }
    setMsg({ tone: 'green', text: 'Saved.' });
    onSaved(res.data);
  }
  return { draft, setDraft, dirty, busy, msg, save, reset: () => setDraft(base) };
}

export default function MatchPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { accessToken } = useAuth();
  const { data, loading, error, refetch } = useApi<AdminMatch>(`/admin/sportsbook/events/${id}/`);
  const { data: detail } = useApi<{ markets: MarketRow[] }>(`/events/${id}/`);
  const [match, setMatch] = useState<AdminMatch | null>(null);
  const [league, setLeague] = useState<LeagueRef | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteMsg, setDeleteMsg] = useState<Msg>(null);

  useEffect(() => { if (data) { setMatch(data); setLeague(data.league_detail); } }, [data]);
  const onSaved = (m: AdminMatch) => { setMatch(m); setLeague(m.league_detail); };
  const names = match ? teamNames(match) : { home: '', away: '' };

  const details = useSection({
    home: names.home, away: names.away, sport: match?.sport ?? 'football',
    starts_at: toLocalInput(match?.starts_at ?? null), featured: !!match?.featured, is_open: !!match?.is_open,
    league: match?.league ?? null as number | null,
  }, match, onSaved);
  const prices = useSection({
    odds: match?.odds ?? '', odds_draw: match?.odds_draw ?? '', odds_away: match?.odds_away ?? '',
    has_odds: !!match?.has_odds, prices_locked: !!match?.prices_locked,
  }, match, onSaved);
  const live = useSection({
    status: match?.status ?? '', elapsed: match?.elapsed?.toString() ?? '',
    score_home: match?.score_home?.toString() ?? '', score_away: match?.score_away?.toString() ?? '',
    ht_score_home: match?.ht_score_home?.toString() ?? '', ht_score_away: match?.ht_score_away?.toString() ?? '',
  }, match, onSaved);

  if (loading && !match) return <LoadingState className="py-24" label="Loading match…" />;
  if (error || !match) {
    return <EmptyState icon={BsCalendar2Week} title="Match not found" action={<Btn onClick={() => router.push('/sportsbook/matches')}>Back to matches</Btn>} />;
  }

  const num = (v: string) => (v === '' ? null : Number(v));
  const leagueDirty = (league?.id ?? null) !== (match.league ?? null);
  const markets = detail?.markets ?? [];

  async function remove() {
    if (!accessToken || !match || !confirm(`Delete ${match.name}? This can't be undone.`)) return;
    setDeleting(true);
    const res = await authedRequest('DELETE', `/admin/sportsbook/events/${match.id}/`, accessToken);
    setDeleting(false);
    if (res.error) { setDeleteMsg({ tone: 'red', text: res.error }); return; }
    router.push('/sportsbook/matches');
  }

  return (
    <div className="space-y-6">
      <Link href="/sportsbook/matches" className="inline-flex items-center gap-2 text-sm font-semibold text-muted-foreground hover:text-foreground">
        <BsArrowLeft size={13} /> All matches
      </Link>

      {/* Scoreboard header */}
      <section className="relative overflow-hidden rounded-3xl border border-border/70 bg-[radial-gradient(120%_120%_at_0%_0%,#3a2fa8_0%,#1d1660_45%,#0d0a2a_100%)] p-6 text-white shadow-xl sm:p-8">
        <div className="pointer-events-none absolute -right-20 -top-24 h-72 w-72 rounded-full bg-[#6C63E8]/30 blur-3xl" />
        <div className="relative flex flex-wrap items-center gap-2">
          <LeagueTag league={match.league_detail} className="text-white/75" />
          <span className="ml-auto flex flex-wrap items-center gap-2"><SourceBadge m={match} /><StateBadge m={match} /></span>
        </div>
        <div className="relative mt-6 grid grid-cols-[1fr_auto_1fr] items-center gap-4">
          <div className="flex flex-col items-center gap-2 text-center">
            <TeamCrest team={match.home_team} name={names.home} size={56} />
            <p className="text-lg font-extrabold sm:text-xl">{names.home}</p>
          </div>
          <div className="text-center">
            {match.score_home != null && match.score_away != null && match.state !== 'upcoming' ? (
              <p className="font-mono text-4xl font-black tabular-nums sm:text-5xl">{match.score_home} – {match.score_away}</p>
            ) : (
              <p className="text-2xl font-black text-white/50">VS</p>
            )}
            <p className="mt-2 text-xs font-semibold text-white/60">{kickoff(match.starts_at)}</p>
          </div>
          <div className="flex flex-col items-center gap-2 text-center">
            <TeamCrest team={match.away_team} name={names.away} size={56} />
            <p className="text-lg font-extrabold sm:text-xl">{names.away}</p>
          </div>
        </div>
        <div className="relative mt-6 flex flex-wrap gap-2 text-xs">
          <span className="rounded-lg bg-white/10 px-2.5 py-1">{match.markets_count} markets</span>
          <span className="rounded-lg bg-white/10 px-2.5 py-1">{match.bets_count} open bets</span>
          <span className="rounded-lg bg-white/10 px-2.5 py-1">{match.trading.bettable ? 'Taking bets' : 'Not taking bets'}</span>
          {match.prices_locked && <span className="flex items-center gap-1 rounded-lg bg-gold/25 px-2.5 py-1 text-gold"><BsLockFill size={10} /> Manual prices</span>}
        </div>
      </section>

      <div className="grid gap-6 xl:grid-cols-2">
        {/* Details */}
        <Panel title="Match details" description="Teams, league and kick-off as players see them.">
          <div className="space-y-4">
            <div className="grid grid-cols-2 gap-3">
              <Field label="Home team"><TextInput value={details.draft.home} onChange={(e) => details.setDraft({ ...details.draft, home: e.target.value })} /></Field>
              <Field label="Away team"><TextInput value={details.draft.away} onChange={(e) => details.setDraft({ ...details.draft, away: e.target.value })} /></Field>
            </div>
            <Field label="League"><LeaguePicker value={league} onChange={setLeague} /></Field>
            <div className="grid grid-cols-2 gap-3">
              <Field label="Kick-off"><TextInput type="datetime-local" value={details.draft.starts_at} onChange={(e) => details.setDraft({ ...details.draft, starts_at: e.target.value })} /></Field>
              <Field label="Sport">
                <Select value={details.draft.sport} onChange={(e) => details.setDraft({ ...details.draft, sport: e.target.value })}>
                  {SPORTS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
                </Select>
              </Field>
            </div>
            <div className="divide-y divide-border/60 rounded-xl border border-border/70">
              <label className="flex items-center justify-between gap-3 p-3.5 text-sm">
                <span><span className="font-semibold">Open for betting</span><span className="block text-xs text-muted-foreground">Turn off to suspend all betting on this match.</span></span>
                <Switch checked={details.draft.is_open} onChange={(v) => details.setDraft({ ...details.draft, is_open: v })} label="Open for betting" />
              </label>
              <label className="flex items-center justify-between gap-3 p-3.5 text-sm">
                <span><span className="font-semibold">Featured</span><span className="block text-xs text-muted-foreground">Show in Top matches on the sportsbook.</span></span>
                <Switch checked={details.draft.featured} onChange={(v) => details.setDraft({ ...details.draft, featured: v })} label="Featured" />
              </label>
            </div>
            {match.source === 'feed' && (
              <p className="flex gap-2 text-xs text-muted-foreground"><BsInfoCircle className="mt-0.5 shrink-0" size={12} />Team names and league on feed matches can be overwritten by the next feed update.</p>
            )}
          </div>
          <SaveBar
            busy={details.busy} dirty={details.dirty || leagueDirty} msg={details.msg} onReset={() => { details.reset(); setLeague(match.league_detail); }}
            onSave={() => details.save({
              home_team_name: details.draft.home, away_team_name: details.draft.away, sport: details.draft.sport,
              starts_at: fromLocalInput(details.draft.starts_at), featured: details.draft.featured, is_open: details.draft.is_open,
              league: league?.id ?? null,
            })}
          />
        </Panel>

        {/* Prices */}
        <Panel
          title="Match result prices"
          description="The 1 · X · 2 prices on the board and bet slip."
          actions={prices.draft.prices_locked ? <Badge tone="gold"><BsLockFill size={9} /> Locked</Badge> : <Badge tone="indigo"><BsUnlock size={10} /> Feed-driven</Badge>}
        >
          <div className="space-y-4">
            <div className="grid grid-cols-3 gap-3">
              {([['odds', '1 · Home'], ['odds_draw', 'X · Draw'], ['odds_away', '2 · Away']] as const).map(([k, label]) => (
                <Field key={k} label={label}>
                  <TextInput
                    type="number" step="0.01" min="1" className="text-center font-mono text-lg font-bold"
                    value={prices.draft[k] ?? ''} onChange={(e) => prices.setDraft({ ...prices.draft, [k]: e.target.value })}
                  />
                </Field>
              ))}
            </div>
            {match.previous_odds && <p className="text-xs text-muted-foreground">Home price was {match.previous_odds} before the last change.</p>}
            <div className="divide-y divide-border/60 rounded-xl border border-border/70">
              <label className="flex items-center justify-between gap-3 p-3.5 text-sm">
                <span><span className="font-semibold">Priced and visible</span><span className="block text-xs text-muted-foreground">Off hides the match from players until it has real prices.</span></span>
                <Switch checked={prices.draft.has_odds} onChange={(v) => prices.setDraft({ ...prices.draft, has_odds: v })} label="Priced" />
              </label>
              <label className="flex items-center justify-between gap-3 p-3.5 text-sm">
                <span>
                  <span className="font-semibold">Lock prices</span>
                  <span className="block text-xs text-muted-foreground">The odds feed won&apos;t change the 1X2 or markets. Scores still update.</span>
                </span>
                <Switch checked={prices.draft.prices_locked} onChange={(v) => prices.setDraft({ ...prices.draft, prices_locked: v })} label="Lock prices" />
              </label>
            </div>
            {match.source === 'feed' && !prices.draft.prices_locked && prices.dirty && (
              <Notice tone="indigo">Lock prices too, or the feed will replace your prices on its next update.</Notice>
            )}
          </div>
          <SaveBar
            busy={prices.busy} dirty={prices.dirty} msg={prices.msg} onReset={prices.reset}
            onSave={() => prices.save({
              odds: prices.draft.odds || '1.00', odds_draw: prices.draft.odds_draw || null, odds_away: prices.draft.odds_away || null,
              has_odds: prices.draft.has_odds, prices_locked: prices.draft.prices_locked,
            })}
          />
        </Panel>
      </div>

      {/* Live score */}
      <Panel
        title={<span className="flex items-center gap-2"><BsBroadcast size={14} className="text-live" />Live score & status</span>}
        description="Correct the scoreboard by hand. Changing the score here doesn't settle bets; use Result & settlement below."
      >
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Field label="Status">
            <Select value={live.draft.status} onChange={(e) => live.setDraft({ ...live.draft, status: e.target.value })}>
              {STATUSES.map((s) => <option key={s.id || 'none'} value={s.id}>{s.label}</option>)}
            </Select>
          </Field>
          <Field label="Minute"><TextInput type="number" min={0} max={130} value={live.draft.elapsed} onChange={(e) => live.setDraft({ ...live.draft, elapsed: e.target.value })} placeholder="—" /></Field>
          <Field label="Score">
            <div className="flex items-center gap-2">
              <TextInput type="number" min={0} className="text-center" value={live.draft.score_home} onChange={(e) => live.setDraft({ ...live.draft, score_home: e.target.value })} aria-label="Home score" />
              <span className="text-muted-foreground">–</span>
              <TextInput type="number" min={0} className="text-center" value={live.draft.score_away} onChange={(e) => live.setDraft({ ...live.draft, score_away: e.target.value })} aria-label="Away score" />
            </div>
          </Field>
          <Field label="Half-time score">
            <div className="flex items-center gap-2">
              <TextInput type="number" min={0} className="text-center" value={live.draft.ht_score_home} onChange={(e) => live.setDraft({ ...live.draft, ht_score_home: e.target.value })} aria-label="Half-time home score" />
              <span className="text-muted-foreground">–</span>
              <TextInput type="number" min={0} className="text-center" value={live.draft.ht_score_away} onChange={(e) => live.setDraft({ ...live.draft, ht_score_away: e.target.value })} aria-label="Half-time away score" />
            </div>
          </Field>
        </div>
        <SaveBar
          busy={live.busy} dirty={live.dirty} msg={live.msg} onReset={live.reset}
          onSave={() => live.save({
            status: live.draft.status, elapsed: num(live.draft.elapsed),
            score_home: num(live.draft.score_home), score_away: num(live.draft.score_away),
            ht_score_home: num(live.draft.ht_score_home), ht_score_away: num(live.draft.ht_score_away),
          })}
        />
      </Panel>

      {accessToken && <SettlePanel eventId={match.id} eventName={match.name} token={accessToken} onDone={refetch} />}

      {/* Markets */}
      <Panel title={<span className="flex items-center gap-2"><BsCash size={14} />Markets</span>} description="Every market on this match and its current prices." padded={markets.length === 0}>
        {markets.length === 0 ? (
          <p className="text-sm text-muted-foreground">No extra markets — only the match result.</p>
        ) : (
          <div className="grid gap-px bg-border/50 sm:grid-cols-2 xl:grid-cols-3">
            {markets.map((m) => (
              <div key={m.id} className="bg-card p-4">
                <div className="mb-2 flex items-start justify-between gap-2">
                  <p className="text-[13px] font-semibold">{m.name}</p>
                  {m.settled ? <Badge tone="slate">Settled</Badge> : m.needs_review ? <Badge tone="gold">Review</Badge> : m.is_open ? <Badge tone="green">Open</Badge> : <Badge tone="slate">Suspended</Badge>}
                </div>
                <div className="flex flex-wrap gap-1.5">
                  {m.outcomes.map((o) => (
                    <span key={o.id} className={cx(
                      'rounded-lg px-2 py-1 text-xs',
                      o.result === 'won' ? 'bg-win/15 text-win' : o.result === 'lost' ? 'bg-muted/40 text-muted-foreground line-through' : 'bg-muted/70',
                    )}>
                      {o.label} <span className="font-mono font-bold">{Number(o.odds).toFixed(2)}</span>
                    </span>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
      </Panel>

      <Panel title="Danger zone" className="border-live/30">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <p className="text-sm text-muted-foreground">Delete only matches created by mistake. Matches with bets can&apos;t be deleted — suspend or void them instead.</p>
          <Btn variant="danger" icon={BsTrash3} busy={deleting} onClick={remove}>Delete match</Btn>
        </div>
        {deleteMsg && <div className="mt-3"><Notice tone={deleteMsg.tone}>{deleteMsg.text}</Notice></div>}
      </Panel>
    </div>
  );
}
