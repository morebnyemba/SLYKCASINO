'use client';

import { useState } from 'react';
import { BsCheck2Circle, BsFlag } from 'react-icons/bs';
import { Badge, Btn, Notice, Panel, TextInput, cx } from '@/components/console/ui';
import { authedPost, useApi } from '@/lib/use-api';

interface Outcome { id: number; label: string; odds: string; result: string }
export interface MarketRow {
  id: number; name: string; kind: string; group: string; settled: boolean; is_open: boolean; needs_review: boolean; outcomes: Outcome[];
}
interface EventDetail { markets: MarketRow[] }

const SCORE_ROWS = [
  ['', 'Full time (90′)', true],
  ['ht', 'Half time', false],
  ['corners', 'Corners', false],
  ['yellow', 'Yellow cards', false],
  ['red', 'Red cards', false],
] as const;

/** Settle a match from its final score, and settle markets the feed couldn't decide. */
export function SettlePanel({ eventId, eventName, token, onDone }: {
  eventId: number; eventName: string; token: string; onDone: () => void;
}) {
  const { data: detail, refetch } = useApi<EventDetail>(`/events/${eventId}/`);
  const [score, setScore] = useState<Record<string, string>>({});
  const [winners, setWinners] = useState<Record<number, number[]>>({});
  const [msg, setMsg] = useState<{ tone: 'green' | 'red'; text: string } | null>(null);
  const [busy, setBusy] = useState(false);

  const markets = detail?.markets ?? [];
  const pending = markets.filter((m) => !m.settled);
  const manual = pending.filter((m) => m.kind === 'manual' || m.needs_review);
  const val = (k: string) => score[k] ?? '';
  const key = (prefix: string, side: 'home' | 'away') => (prefix ? `${prefix}_${side}` : side);

  async function settleScore(e: React.FormEvent) {
    e.preventDefault();
    if (!confirm(`Settle ${eventName} at ${val('home')}–${val('away')}? This pays out bets and can't be undone.`)) return;
    setBusy(true);
    const body: Record<string, number> = { home: Number(val('home')), away: Number(val('away')) };
    for (const [prefix] of SCORE_ROWS) {
      if (!prefix) continue;
      const h = val(`${prefix}_home`), a = val(`${prefix}_away`);
      if (h !== '' && a !== '') { body[`${prefix}_home`] = Number(h); body[`${prefix}_away`] = Number(a); }
    }
    const res = await authedPost<{ bets_settled: number }>(`/events/${eventId}/settle-score/`, body, token);
    setBusy(false);
    setMsg(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: `Settled ${res.data?.bets_settled ?? 0} bet(s) from the score.` });
    refetch(); onDone();
  }

  async function settleMarket(m: MarketRow, voidIt: boolean) {
    const picked = winners[m.id] ?? [];
    if (!voidIt && picked.length === 0) { setMsg({ tone: 'red', text: 'Pick the winning outcome(s) first.' }); return; }
    setBusy(true);
    const res = await authedPost<{ bets_settled: number }>(
      `/events/${eventId}/markets/${m.id}/settle/`, voidIt ? { void: true } : { winners: picked }, token,
    );
    setBusy(false);
    setMsg(res.error ? { tone: 'red', text: res.error } : { tone: 'green', text: `${m.name}: settled ${res.data?.bets_settled ?? 0} bet(s).` });
    refetch(); onDone();
  }

  return (
    <Panel
      title="Result & settlement"
      description="Finished matches settle automatically from the feed. Use this when the feed is down or wrong — it pays out immediately."
      actions={<Badge tone={pending.length ? 'gold' : 'green'}>{pending.length} unsettled market{pending.length === 1 ? '' : 's'}</Badge>}
    >
      <form onSubmit={settleScore} className="space-y-4">
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-5">
          {SCORE_ROWS.map(([prefix, label, required]) => (
            <div key={prefix || 'ft'} className={cx('rounded-xl border border-border/70 p-3', required && 'border-secondary/50 bg-secondary/5')}>
              <p className="mb-2 text-xs font-bold text-muted-foreground">{label}{!required && ' (optional)'}</p>
              <div className="flex items-center gap-2">
                <TextInput required={required} type="number" min={0} className="h-9 text-center" value={val(key(prefix, 'home'))}
                  onChange={(e) => setScore((s) => ({ ...s, [key(prefix, 'home')]: e.target.value }))} aria-label={`${label} home`} />
                <span className="text-muted-foreground">–</span>
                <TextInput required={required} type="number" min={0} className="h-9 text-center" value={val(key(prefix, 'away'))}
                  onChange={(e) => setScore((s) => ({ ...s, [key(prefix, 'away')]: e.target.value }))} aria-label={`${label} away`} />
              </div>
            </div>
          ))}
        </div>
        <Btn variant="primary" type="submit" busy={busy} icon={BsFlag}>Settle from final score</Btn>
      </form>

      {manual.length > 0 && (
        <div className="mt-6 space-y-3">
          <p className="text-sm font-bold">Markets that need a decision</p>
          {manual.map((m) => (
            <div key={m.id} className="rounded-xl border border-gold/30 bg-gold/5 p-4">
              <p className="mb-2.5 text-sm font-semibold">{m.name}</p>
              <div className="mb-3 flex flex-wrap gap-2">
                {m.outcomes.map((o) => {
                  const on = (winners[m.id] ?? []).includes(o.id);
                  return (
                    <button
                      type="button"
                      key={o.id}
                      onClick={() => setWinners((w) => {
                        const cur = new Set(w[m.id] ?? []);
                        if (cur.has(o.id)) cur.delete(o.id); else cur.add(o.id);
                        return { ...w, [m.id]: Array.from(cur) };
                      })}
                      className={cx(
                        'flex items-center gap-2 rounded-lg border px-3 py-1.5 text-xs font-semibold transition-colors',
                        on ? 'border-win bg-win/15 text-win' : 'border-border bg-card hover:border-secondary/60',
                      )}
                    >
                      {on && <BsCheck2Circle size={12} />}
                      {o.label}<span className="font-mono text-muted-foreground">@{o.odds}</span>
                    </button>
                  );
                })}
              </div>
              <div className="flex gap-2">
                <Btn size="sm" variant="success" busy={busy} onClick={() => settleMarket(m, false)}>Settle winners</Btn>
                <Btn size="sm" busy={busy} onClick={() => settleMarket(m, true)}>Void market</Btn>
              </div>
            </div>
          ))}
        </div>
      )}
      {msg && <div className="mt-4"><Notice tone={msg.tone} onClose={() => setMsg(null)}>{msg.text}</Notice></div>}
    </Panel>
  );
}
