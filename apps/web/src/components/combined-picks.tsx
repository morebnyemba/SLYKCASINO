'use client';

import { useEffect, useMemo, useState } from 'react';
import { BsChevronDown, BsLink45Deg } from 'react-icons/bs';
import { useBetslip, type BetLeg, type Selection } from '@/lib/betslip-context';
import { config } from '@/lib/config';
import { formatOdds, useSettings } from '@/lib/settings-context';

interface ComboLeg {
  event_id: number; selection?: Selection; outcome_id?: number; odds: string;
  market_id?: number; market_name?: string; outcome_label?: string; name: string;
}
interface Combo { key: string; group: string; name: string; odds: string; legs: ComboLeg[] }
interface CombosResponse { event_id: number; count: number; groups: string[]; combos: Combo[] }

const SHOWN = 12;

/** Load a match's combined picks (two picks priced together) once the tab is opened. */
export function useCombos(eventId: string | number, enabled: boolean) {
  const [data, setData] = useState<CombosResponse | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!enabled) return;
    let cancelled = false;
    const load = () => fetch(`${config.apiUrl}/events/${eventId}/combos/`, { cache: 'no-store' })
      .then((r) => (r.ok ? r.json() : Promise.reject(r.status)))
      .then((d: CombosResponse) => { if (!cancelled) { setData(d); setFailed(false); } })
      .catch(() => { if (!cancelled) setFailed(true); });
    void load();
    const timer = window.setInterval(load, 30000);          // prices move: refresh while the tab is open
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [eventId, enabled]);
  return { data, failed };
}

/** The Combined tab: ready-made pairs from this match ("Chelsea Win & Over 1.5 Goals") at one price
 *  that allows for how the two picks go together. Tapping one puts both picks on the slip. */
export function CombinedPicks({ eventId, eventName, closed, data, failed }: {
  eventId: string | number; eventName: string; closed: boolean; data: CombosResponse | null; failed: boolean;
}) {
  const { addCombo, isOnSlip, isOutcomeOnSlip, limits } = useBetslip();
  const { oddsFormat } = useSettings();
  const [open, setOpen] = useState<Record<string, boolean>>({});
  const [more, setMore] = useState<Record<string, boolean>>({});
  const byGroup = useMemo(() => {
    const out: Record<string, Combo[]> = {};
    for (const c of data?.combos ?? []) (out[c.group] ??= []).push(c);
    return out;
  }, [data]);

  if (failed && !data) return <p className="rounded-2xl border border-border bg-card p-4 text-sm text-muted-foreground">Combined picks couldn’t load. Try again in a moment.</p>;
  if (!data) {
    return (
      <div className="space-y-2" aria-busy>
        {[0, 1, 2].map((i) => <div key={i} className="h-24 animate-pulse rounded-2xl bg-muted/40" />)}
      </div>
    );
  }
  if (!data.count) {
    return (
      <p className="rounded-2xl border border-border bg-card p-4 text-sm text-muted-foreground">
        No combined picks for this match right now: they are built from the markets that are open, and this match doesn’t have enough of them.
      </p>
    );
  }

  const toLeg = (l: ComboLeg): BetLeg => ({
    eventId, eventName, selection: l.selection ?? 'home', odds: Number(l.odds),
    ...(l.outcome_id != null ? { outcomeId: l.outcome_id, marketId: l.market_id, marketName: l.market_name, outcomeLabel: l.outcome_label } : {}),
  });
  const onSlip = (c: Combo) => c.legs.every((l) => (l.outcome_id != null ? isOutcomeOnSlip(l.outcome_id) : isOnSlip(eventId, l.selection ?? 'home')));

  return (
    <div className="space-y-3">
      <p className="flex items-start gap-2 px-1 text-xs text-muted-foreground">
        <BsLink45Deg size={16} className="mt-px shrink-0 text-secondary" />
        {data.count} combined picks. Both picks must win; the price allows for how they go together. One combined pick per match
        {limits?.maxPerMatch ? ` (at most ${limits.maxPerMatch} picks from a match)` : ''}: tapping another replaces it.
      </p>
      {data.groups.map((g, gi) => {
        const items = byGroup[g] ?? [];
        const isOpen = open[g] ?? gi < 3;
        const shown = more[g] ? items : items.slice(0, SHOWN);
        return (
          <section key={g} className="overflow-hidden rounded-2xl border border-border bg-card">
            <button onClick={() => setOpen((o) => ({ ...o, [g]: !isOpen }))} aria-expanded={isOpen}
              className="flex w-full items-center justify-between gap-2 px-4 py-3 text-left text-sm font-extrabold">
              <span>{g} <span className="ml-1 rounded-full bg-muted px-1.5 text-[10px] font-bold text-muted-foreground">{items.length}</span></span>
              <BsChevronDown size={13} className={`transition-transform ${isOpen ? 'rotate-180' : ''}`} />
            </button>
            {isOpen && (
              <div className="border-t border-border/60 p-2">
                <div className="grid gap-1.5 sm:grid-cols-2">
                  {shown.map((c) => {
                    const active = onSlip(c);
                    return (
                      <button key={c.key} disabled={closed} onClick={() => addCombo(c.legs.map(toLeg))}
                        aria-pressed={active}
                        className={`flex min-h-12 items-center justify-between gap-3 rounded-xl border px-3 py-2 text-left text-[13px] font-semibold transition-colors disabled:opacity-50 ${
                          active ? 'border-secondary bg-secondary text-secondary-foreground' : 'border-border/70 bg-background hover:border-secondary/60'}`}>
                        <span className="min-w-0 leading-snug">{c.name}</span>
                        <span className={`shrink-0 rounded-lg px-2 py-1 text-sm font-extrabold tabular-nums ${active ? 'bg-white/20' : 'bg-muted'}`}>
                          {formatOdds(Number(c.odds), oddsFormat)}
                        </span>
                      </button>
                    );
                  })}
                </div>
                {items.length > SHOWN && (
                  <button onClick={() => setMore((m) => ({ ...m, [g]: !m[g] }))}
                    className="mt-2 w-full rounded-xl py-2 text-xs font-bold text-secondary hover:bg-muted">
                    {more[g] ? 'Show fewer' : `Show all ${items.length}`}
                  </button>
                )}
              </div>
            )}
          </section>
        );
      })}
    </div>
  );
}
