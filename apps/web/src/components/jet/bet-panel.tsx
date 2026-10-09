'use client';

import { useEffect, useRef, useState } from 'react';
import { BsDash, BsPlus } from 'react-icons/bs';
import { Spinner } from '@slyk/ui/components/spinner';
import { fmtX, type JetBet, type JetRound, type JetSettings } from '@/lib/jet';

const money = (v: number) => `$${v.toFixed(2)}`;

/**
 * One of the two bet slots. During the countdown it places (or cancels) a bet;
 * in flight it becomes the cash-out button. A bet pressed while a round is
 * flying waits and goes on the next round. Auto bet re-places the same bet
 * every round; auto cash-out sends the target with the bet so the server
 * cashes it out even if this tab is closed.
 */
export function BetPanel({ slot, settings, round, bet, multiplier, loggedIn, onPlace, onCancel, onCashOut }: {
  slot: number;
  settings: JetSettings;
  round: JetRound | null;
  bet: JetBet | undefined;
  multiplier: number;
  loggedIn: boolean;
  onPlace: (stake: string, auto: string | null) => Promise<{ error?: string }>;
  onCancel: (id: number) => Promise<{ error?: string }>;
  onCashOut: (id: number) => Promise<{ error?: string }>;
}) {
  const min = Number(settings.min_bet);
  const max = Number(settings.max_bet);
  const [tab, setTab] = useState<'bet' | 'auto'>('bet');
  const [stake, setStake] = useState(() => Math.max(min, 1).toFixed(2));
  const [autoCash, setAutoCash] = useState(false);
  const [autoAt, setAutoAt] = useState('2.00');
  const [autoBet, setAutoBet] = useState(false);
  const [queued, setQueued] = useState(false);
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<{ tone: 'ok' | 'err'; text: string } | null>(null);
  const placedFor = useRef<number | null>(null);

  const betting = round?.status === 'betting';
  const flying = round?.status === 'flying';
  const stakeNum = Number(stake) || 0;
  const quick = [min, 1, 5, 10, 20, 50].filter((v, i, a) => v >= min && v <= max && a.indexOf(v) === i).slice(0, 4);

  async function place() {
    if (!round) return;
    setBusy(true); setNote(null);
    const res = await onPlace(stakeNum.toFixed(2), autoCash ? Number(autoAt).toFixed(2) : null);
    setBusy(false);
    placedFor.current = round.id;
    if (res.error) { setNote({ tone: 'err', text: res.error }); setAutoBet(false); }
  }

  // A queued bet, or auto bet, goes on as soon as the next countdown opens.
  useEffect(() => {
    if (!betting || !round || bet || busy || placedFor.current === round.id) return;
    if (queued || autoBet) {
      setQueued(false);
      void place();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [betting, round?.id, bet, queued, autoBet]);

  async function press() {
    if (!loggedIn) { window.location.href = '/login'; return; }
    setNote(null);
    if (bet && bet.status === 'active') {
      setBusy(true);
      const res = flying ? await onCashOut(bet.id) : await onCancel(bet.id);
      setBusy(false);
      if (res.error) setNote({ tone: 'err', text: res.error });
      return;
    }
    if (queued) { setQueued(false); return; }
    if (stakeNum < min || stakeNum > max) { setNote({ tone: 'err', text: `Bets are ${money(min)}–${money(max)}.` }); return; }
    if (autoCash && (Number(autoAt) < 1.01 || !Number.isFinite(Number(autoAt)))) { setNote({ tone: 'err', text: 'Auto cash-out must be at least 1.01x.' }); return; }
    if (betting) await place();
    else setQueued(true);
  }

  const active = bet?.status === 'active';
  let label: React.ReactNode;
  let sub = '';
  let cls = 'bg-[#22c55e] hover:bg-[#16a34a] text-white';
  if (active && flying) {
    const value = Math.min(Number(bet!.stake) * multiplier, Number(settings.max_win));
    label = <>Cash out <span className="block text-2xl font-black tabular-nums">{money(value)}</span></>;
    cls = 'bg-[#f59e0b] hover:bg-[#d97706] text-black';
  } else if (active) {
    label = 'Cancel';
    sub = `${money(Number(bet!.stake))} on this round`;
    cls = 'bg-[#ef4444] hover:bg-[#dc2626] text-white';
  } else if (queued) {
    label = 'Cancel';
    sub = 'Waiting for next round';
    cls = 'bg-[#ef4444] hover:bg-[#dc2626] text-white';
  } else {
    label = <>Bet <span className="block text-2xl font-black tabular-nums">{money(stakeNum)}</span></>;
    if (!betting) sub = 'Goes on the next round';
  }
  const locked = active || queued;

  return (
    <section className="rounded-2xl border border-white/5 bg-[#1b1530] p-3 text-white">
      <div className="mx-auto mb-3 flex w-fit rounded-full bg-black/30 p-0.5 text-xs font-bold">
        {(['bet', 'auto'] as const).map((t) => (
          <button key={t} onClick={() => setTab(t)}
            className={`rounded-full px-5 py-1 capitalize transition-colors ${tab === t ? 'bg-white/15 text-white' : 'text-white/50'}`}>
            {t}
          </button>
        ))}
      </div>

      <div className="flex gap-3">
        <div className="w-[46%] min-w-0 space-y-2">
          <div className="flex items-center rounded-full bg-black/40 px-1.5 py-1">
            <button disabled={locked} aria-label="Less" onClick={() => setStake((v) => Math.max(min, (Number(v) || 0) - 1).toFixed(2))}
              className="flex h-7 w-7 items-center justify-center rounded-full bg-white/10 disabled:opacity-40"><BsDash /></button>
            <input
              value={stake} disabled={locked} inputMode="decimal" aria-label={`Bet ${slot} stake`}
              onChange={(e) => setStake(e.target.value.replace(/[^0-9.]/g, ''))}
              onBlur={() => setStake((v) => Math.min(max, Math.max(min, Number(v) || min)).toFixed(2))}
              className="min-w-0 flex-1 bg-transparent text-center text-base font-extrabold tabular-nums outline-none disabled:opacity-60"
            />
            <button disabled={locked} aria-label="More" onClick={() => setStake((v) => Math.min(max, (Number(v) || 0) + 1).toFixed(2))}
              className="flex h-7 w-7 items-center justify-center rounded-full bg-white/10 disabled:opacity-40"><BsPlus /></button>
          </div>
          <div className="grid grid-cols-2 gap-1.5">
            {quick.map((v) => (
              <button key={v} disabled={locked} onClick={() => setStake(v.toFixed(2))}
                className="rounded-full bg-black/30 py-1 text-xs font-bold text-white/70 hover:text-white disabled:opacity-40">
                {money(v)}
              </button>
            ))}
          </div>
        </div>
        <button
          onClick={press} disabled={busy}
          className={`flex min-h-[86px] flex-1 flex-col items-center justify-center rounded-2xl px-2 text-center text-base font-extrabold uppercase shadow-lg transition-colors disabled:opacity-70 ${cls}`}
        >
          {busy ? <Spinner size={18} /> : label}
          {sub && <span className="mt-0.5 text-[10.5px] font-semibold normal-case opacity-90">{sub}</span>}
        </button>
      </div>

      {tab === 'auto' && (
        <div className="mt-3 flex flex-wrap items-center justify-between gap-3 border-t border-white/5 pt-3 text-xs font-bold text-white/70">
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={autoBet} onChange={(e) => setAutoBet(e.target.checked)} className="h-4 w-4 accent-[#22c55e]" />
            Auto bet
          </label>
          <label className="flex items-center gap-2">
            <input type="checkbox" checked={autoCash} disabled={locked} onChange={(e) => setAutoCash(e.target.checked)} className="h-4 w-4 accent-[#f59e0b]" />
            Auto cash out
            <input
              value={autoAt} disabled={!autoCash || locked} inputMode="decimal" aria-label="Auto cash-out multiplier"
              onChange={(e) => setAutoAt(e.target.value.replace(/[^0-9.]/g, ''))}
              className="w-16 rounded-full bg-black/40 px-2 py-1 text-center text-white outline-none disabled:opacity-40"
            />
            x
          </label>
        </div>
      )}

      {bet?.status === 'cashed' && (
        <p className="mt-2 text-center text-xs font-bold text-[#22c55e]">
          Cashed out at {fmtX(bet.cashout_multiplier)} · won {money(Number(bet.payout))}
        </p>
      )}
      {active && bet?.auto_cashout && (
        <p className="mt-2 text-center text-xs font-semibold text-white/60">Auto cash-out at {fmtX(bet.auto_cashout)}</p>
      )}
      {note && <p className={`mt-2 text-center text-xs font-semibold ${note.tone === 'err' ? 'text-[#f87171]' : 'text-[#22c55e]'}`}>{note.text}</p>}
    </section>
  );
}
