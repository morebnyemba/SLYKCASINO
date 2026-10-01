'use client';

import { Fragment, useState } from 'react';
import { FaCalendarAlt } from 'react-icons/fa';
import { Card, CardContent, CardHeader, CardTitle } from '@slyk/ui/components/card';
import { Badge } from '@slyk/ui/components/badge';
import { Button } from '@slyk/ui/components/button';
import { Input } from '@slyk/ui/components/input';
import { useAuth } from '@/lib/auth-context';
import { useApi, authedPost } from '@/lib/use-api';
import { config } from '@/lib/config';

interface Team { id: number; name: string }

interface Event {
  id: number;
  name: string;
  sport: string;
  home_team: Team | null;
  away_team: Team | null;
  starts_at: string | null;
  is_open: boolean;
  status: string;
  score_home: number | null;
  score_away: number | null;
  odds: string;
  odds_draw: string | null;
  odds_away: string | null;
  markets_count: number;
}

interface Outcome { id: number; label: string; odds: string; result: string }
interface Market {
  id: number; name: string; kind: string; settled: boolean; is_open: boolean; needs_review: boolean; outcomes: Outcome[];
}
interface EventDetail extends Event { markets: Market[] }

interface EventsResponse {
  count?: number;
  next?: string | null;
  previous?: string | null;
  results?: Event[];
}

const BLANK = { name: '', sport: 'football', starts_at: '', odds: '', odds_draw: '', odds_away: '' };

/** Settle one event: final score (settles 1X2 + every score-based market) and manual markets. */
function SettlePanel({ event, token, onDone }: { event: Event; token: string; onDone: () => void }) {
  const { data: detail, refetch } = useApi<EventDetail>(`/events/${event.id}/`);
  const [score, setScore] = useState({
    home: '', away: '', ht_home: '', ht_away: '',
    corners_home: '', corners_away: '', yellow_home: '', yellow_away: '', red_home: '', red_away: '',
  });
  const [winners, setWinners] = useState<Record<number, number[]>>({});
  const [msg, setMsg] = useState('');
  const [busy, setBusy] = useState(false);

  const pending = (detail?.markets ?? []).filter((m) => !m.settled);
  // Everything else settles automatically; these need a person.
  const manual = pending.filter((m) => m.kind === 'manual' || m.needs_review);

  async function settleScore(e: React.FormEvent) {
    e.preventDefault();
    if (!confirm(`Settle ${event.name} at ${score.home}-${score.away}? This pays out bets and can't be undone.`)) return;
    setBusy(true);
    const body: Record<string, number> = { home: Number(score.home), away: Number(score.away) };
    for (const prefix of ['ht', 'corners', 'yellow', 'red'] as const) {
      const h = score[`${prefix}_home`];
      const a = score[`${prefix}_away`];
      if (h !== '' && a !== '') {
        body[`${prefix}_home`] = Number(h);
        body[`${prefix}_away`] = Number(a);
      }
    }
    const res = await authedPost<{ bets_settled: number }>(`/events/${event.id}/settle-score/`, body, token);
    setBusy(false);
    setMsg(res.error ? `Error: ${res.error}` : `Settled ${res.data?.bets_settled ?? 0} bet(s).`);
    refetch();
    onDone();
  }

  async function settleMarket(market: Market, voidIt: boolean) {
    const picked = winners[market.id] ?? [];
    if (!voidIt && picked.length === 0) { setMsg('Pick the winning outcome(s) first.'); return; }
    setBusy(true);
    const res = await authedPost<{ bets_settled: number }>(
      `/events/${event.id}/markets/${market.id}/settle/`, voidIt ? { void: true } : { winners: picked }, token,
    );
    setBusy(false);
    setMsg(res.error ? `Error: ${res.error}` : `${market.name}: settled ${res.data?.bets_settled ?? 0} bet(s).`);
    refetch();
  }

  function toggleWinner(marketId: number, outcomeId: number) {
    setWinners((w) => {
      const cur = new Set(w[marketId] ?? []);
      if (cur.has(outcomeId)) cur.delete(outcomeId); else cur.add(outcomeId);
      return { ...w, [marketId]: Array.from(cur) };
    });
  }

  return (
    <div className="space-y-4 bg-muted/30 p-4">
      <form onSubmit={settleScore} className="flex flex-wrap items-end gap-3">
        <div>
          <p className="mb-1 text-xs font-semibold text-muted-foreground">Final score (90&apos;)</p>
          <div className="flex items-center gap-1.5">
            <Input required type="number" min={0} className="w-16" value={score.home} onChange={(e) => setScore({ ...score, home: e.target.value })} />
            <span>–</span>
            <Input required type="number" min={0} className="w-16" value={score.away} onChange={(e) => setScore({ ...score, away: e.target.value })} />
          </div>
        </div>
        <div>
          <p className="mb-1 text-xs font-semibold text-muted-foreground">Half-time (optional, settles half markets)</p>
          <div className="flex items-center gap-1.5">
            <Input type="number" min={0} className="w-16" value={score.ht_home} onChange={(e) => setScore({ ...score, ht_home: e.target.value })} />
            <span>–</span>
            <Input type="number" min={0} className="w-16" value={score.ht_away} onChange={(e) => setScore({ ...score, ht_away: e.target.value })} />
          </div>
        </div>
        {([['corners', 'Corners'], ['yellow', 'Yellow cards'], ['red', 'Red cards']] as const).map(([prefix, label]) => (
          <div key={prefix}>
            <p className="mb-1 text-xs font-semibold text-muted-foreground">{label} (optional)</p>
            <div className="flex items-center gap-1.5">
              <Input type="number" min={0} className="w-16" value={score[`${prefix}_home`]}
                onChange={(e) => setScore({ ...score, [`${prefix}_home`]: e.target.value })} />
              <span>–</span>
              <Input type="number" min={0} className="w-16" value={score[`${prefix}_away`]}
                onChange={(e) => setScore({ ...score, [`${prefix}_away`]: e.target.value })} />
            </div>
          </div>
        ))}
        <Button type="submit" disabled={busy}>Settle from score</Button>
      </form>
      <p className="text-xs text-muted-foreground">
        Finished matches settle automatically from the provider feed (score, corners, cards, goal events).
        Use this only if the feed is unavailable or wrong.
      </p>

      <p className="text-xs text-muted-foreground">
        {pending.length} unsettled market(s){manual.length > 0 && `, ${manual.length} need review (automatic settlement couldn't decide them)`}.
      </p>

      {manual.map((m) => (
        <div key={m.id} className="rounded-lg border border-border bg-card p-3">
          <p className="mb-2 text-sm font-semibold">{m.name}</p>
          <div className="mb-2 flex flex-wrap gap-2">
            {m.outcomes.map((o) => (
              <label key={o.id} className="flex cursor-pointer items-center gap-1.5 rounded-md border border-border px-2 py-1 text-xs">
                <input
                  type="checkbox"
                  checked={(winners[m.id] ?? []).includes(o.id)}
                  onChange={() => toggleWinner(m.id, o.id)}
                />
                {o.label} <span className="font-mono text-muted-foreground">@{o.odds}</span>
              </label>
            ))}
          </div>
          <div className="flex gap-2">
            <Button size="sm" disabled={busy} onClick={() => settleMarket(m, false)}>Settle winners</Button>
            <Button size="sm" variant="outline" disabled={busy} onClick={() => settleMarket(m, true)}>Void market</Button>
          </div>
        </div>
      ))}

      {msg && <p className="text-sm font-medium">{msg}</p>}
    </div>
  );
}

export default function EventsPage() {
  const { accessToken } = useAuth();
  const [page, setPage] = useState(1);
  const { data, loading, refetch } = useApi<EventsResponse>(`/events/?page_size=200&page=${page}`);
  const events = data?.results ?? [];

  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState({ ...BLANK });
  const [saving, setSaving] = useState(false);
  const [formError, setFormError] = useState('');
  const [settling, setSettling] = useState<number | null>(null);

  const set = (k: string, v: string) => setForm((f) => ({ ...f, [k]: v }));

  async function handleCreate(e: React.FormEvent) {
    e.preventDefault();
    if (!accessToken) return;
    setSaving(true);
    setFormError('');
    const body = {
      name: form.name, sport: form.sport, odds: form.odds,
      odds_draw: form.odds_draw || null, odds_away: form.odds_away || null,
      starts_at: form.starts_at ? new Date(form.starts_at).toISOString() : null,
    };
    const { error } = await authedPost('/events/', body, accessToken);
    setSaving(false);
    if (error) { setFormError(error); return; }
    setShowForm(false);
    setForm({ ...BLANK });
    refetch();
  }

  async function handleSuspend(event: Event) {
    if (!accessToken) return;
    await fetch(`${config.apiUrl}/events/${event.id}/`, {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${accessToken}` },
      body: JSON.stringify({ is_open: !event.is_open }),
    });
    refetch();
  }

  async function handleDelete(id: number) {
    if (!accessToken || !confirm('Delete this event?')) return;
    await fetch(`${config.apiUrl}/events/${id}/`, {
      method: 'DELETE',
      headers: { Authorization: `Bearer ${accessToken}` },
    });
    refetch();
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-full bg-gold/15 text-gold">
            <FaCalendarAlt size={13} />
          </span>
          <div>
            <h1 className="text-2xl font-bold">Events</h1>
            <p className="text-muted-foreground text-sm">Manage sportsbook events, odds and settlement.</p>
          </div>
        </div>
        <Button
          onClick={() => setShowForm((v) => !v)}
          className={showForm ? '' : 'bg-gradient-to-br from-gold to-gold/70 text-gold-foreground hover:opacity-90'}
        >
          {showForm ? 'Cancel' : '+ New event'}
        </Button>
      </div>

      {showForm && (
        <Card className="rounded-2xl border-gold/15">
          <CardHeader><CardTitle className="text-base">Create event</CardTitle></CardHeader>
          <CardContent>
            <form onSubmit={handleCreate} className="grid gap-3 sm:grid-cols-2">
              {[
                { label: 'Name', key: 'name', type: 'text', placeholder: 'Man Utd vs Arsenal', required: true },
                { label: 'Sport', key: 'sport', type: 'text', placeholder: 'football', required: true },
                { label: 'Starts at', key: 'starts_at', type: 'datetime-local', placeholder: '', required: false },
                { label: 'Odds home (1)', key: 'odds', type: 'number', placeholder: '1.90', required: true },
                { label: 'Odds draw (X)', key: 'odds_draw', type: 'number', placeholder: '3.50', required: false },
                { label: 'Odds away (2)', key: 'odds_away', type: 'number', placeholder: '4.20', required: false },
              ].map(({ label, key, type, placeholder, required }) => (
                <div key={key} className="space-y-1">
                  <label className="text-sm font-medium">{label}</label>
                  <Input
                    type={type}
                    required={required}
                    value={form[key as keyof typeof form]}
                    onChange={(e) => set(key, e.target.value)}
                    placeholder={placeholder}
                    step={type === 'number' ? '0.01' : undefined}
                  />
                </div>
              ))}
              {formError && <p className="col-span-2 text-sm text-red-500">{formError}</p>}
              <div className="col-span-2">
                <Button type="submit" disabled={saving}>
                  {saving ? 'Creating…' : 'Create event'}
                </Button>
              </div>
            </form>
          </CardContent>
        </Card>
      )}

      <Card className="rounded-2xl border-gold/15">
        <CardContent className="overflow-x-auto p-0">
          {loading && <p className="p-4 text-sm text-muted-foreground">Loading events…</p>}
          {!loading && events.length === 0 && (
            <p className="p-4 text-sm text-muted-foreground">No events. Create one above.</p>
          )}
          {events.length > 0 && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border text-left text-muted-foreground">
                  <th className="px-4 py-3 font-medium">Event</th>
                  <th className="px-4 py-3 font-medium">Sport</th>
                  <th className="px-4 py-3 font-medium">Starts</th>
                  <th className="px-4 py-3 font-medium">1 / X / 2</th>
                  <th className="px-4 py-3 font-medium">Markets</th>
                  <th className="px-4 py-3 font-medium">Status</th>
                  <th className="px-4 py-3 font-medium">Actions</th>
                </tr>
              </thead>
              <tbody>
                {events.map((ev) => (
                  <Fragment key={ev.id}>
                    <tr className="border-b border-border last:border-0">
                      <td className="px-4 py-3 font-medium">
                        {ev.name}
                        {ev.score_home != null && ev.score_away != null && (
                          <span className="ml-2 font-mono text-xs text-muted-foreground">{ev.score_home}–{ev.score_away}</span>
                        )}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{ev.sport}</td>
                      <td className="px-4 py-3 text-muted-foreground">
                        {ev.starts_at ? new Date(ev.starts_at).toLocaleString() : '—'}
                      </td>
                      <td className="px-4 py-3 font-mono text-xs">
                        {ev.odds} / {ev.odds_draw ?? '—'} / {ev.odds_away ?? '—'}
                      </td>
                      <td className="px-4 py-3 text-muted-foreground">{ev.markets_count}</td>
                      <td className="px-4 py-3">
                        <Badge variant={ev.is_open ? 'default' : 'secondary'}>
                          {ev.status || (ev.is_open ? 'open' : 'closed')}
                        </Badge>
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex gap-2">
                          <Button size="sm" variant="outline" onClick={() => setSettling(settling === ev.id ? null : ev.id)}>
                            {settling === ev.id ? 'Close' : 'Settle'}
                          </Button>
                          <Button size="sm" variant="outline" onClick={() => handleSuspend(ev)}>
                            {ev.is_open ? 'Suspend' : 'Reopen'}
                          </Button>
                          <Button size="sm" variant="destructive" onClick={() => handleDelete(ev.id)}>
                            Delete
                          </Button>
                        </div>
                      </td>
                    </tr>
                    {settling === ev.id && accessToken && (
                      <tr className="border-b border-border">
                        <td colSpan={7} className="p-0">
                          <SettlePanel event={ev} token={accessToken} onDone={refetch} />
                        </td>
                      </tr>
                    )}
                  </Fragment>
                ))}
              </tbody>
            </table>
          )}
          {(data?.previous || data?.next) && (
            <div className="flex items-center justify-end gap-2 border-t border-border p-4 text-sm text-muted-foreground">
              <span className="mr-auto">{data?.count ?? 0} events · page {page}</span>
              <Button size="sm" variant="outline" disabled={!data?.previous} onClick={() => setPage((p) => p - 1)}>
                Previous
              </Button>
              <Button size="sm" variant="outline" disabled={!data?.next} onClick={() => setPage((p) => p + 1)}>
                Next
              </Button>
            </div>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
